// 2.5D diorama of the 510 Spadina route. Route geometry from route.json is rotated so the
// Spadina leg runs left-to-right, smoothed into clean curves, and laid flat on a lightly tilted
// ground. Cars travel rightward along Spadina; at the right end the line bends up to the lake
// and hooks back to Union. Cars are Flexity Outlook models (it's actually a 501!) oriented to
// the track tangent so they corner naturally, sized to read well at default framing but scaling
// with zoom. Every position is replayed from sim.json. Camera supports pan, swing and tilt
// for exploring, with a double-click reset.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const CARD = 0xf0ebe0; // the ground the route sits on
const ROW = 0xe4dac4; // the right-of-way
const RAIL = 0xc7b89a; // the centreline
const INK = 0xb63333;
const MUTED = 0x9c9384;
const TODAY = 0x981616; // TTC red

const TRAM_PX = 105; // on-screen length of a car

const MODEL_URL = "assets/streetcar.glb"; // the merged Flexity Outlook
const NOSE_SIGN = 2; //

const FIT_W = 1000; // world width the Spadina axis is scaled to
const ROW_HALF = 22; // half width of the right-of-way band, in world units
const TILT = THREE.MathUtils.degToRad(22); // camera elevation

const UNION_STOP_S = 0.975; // cars pull in and stop here (union)

const MAJORS = new Set([
  "spadina_stn",
  "college",
  "dundas",
  "queen",
  "king",
  "union",
]);

// ----x-----x-----x------x----------x------x-------x--------x----x-----x-----x------x----------x------x-------x--------x

export class Diorama {
  constructor(container) {
    this.container = container;
    this.scenarioKey = "today";

    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setClearColor(CARD, 1); // the diorama runs full bleed, no white margins
    container.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();

    // Cars are lit PBR meshes; everything else uses unlit basic material.
    // Studio-style lighting: a bright hemisphere keeps the TTC livery even and clean with no
    // blown-out specular on the glossy roof; one low, soft key from the camera side adds form
    // without an overhead hotspot.
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0xe7dfce, 3.0));
    const key = new THREE.DirectionalLight(0xffffff, 1.1);
    key.position.set(-0.3, 0.7, 1.0); // low and front, so the red roof keeps its colour
    this.scene.add(key);

    // Orthographic camera keeps equal distances equal on screen — essential for a distance-true
    // corridor — tilted down by a fixed elevation for a little depth.
    this.camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 500, 6000);
    this.frustumH = 900;

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    // With real 3D car models, the reader can pan, zoom in to inspect a car, swing the camera to
    // either side, and tilt from near top-down to almost side-on. Limits keep the line from
    // flipping fully backwards; double-click anywhere snaps back to the editorial overview.
    this.controls.enablePan = true;
    this.controls.screenSpacePanning = true; // pan in the view plane, which feels natural in 2.5D
    this.controls.zoomToCursor = true; // zoom toward whatever the reader points at
    this.controls.minZoom = 0.7; // a little room to pull back past the fitted whole-line view
    this.controls.maxZoom = 12.0; // close enough to inspect a single car
    this.controls.minPolarAngle = THREE.MathUtils.degToRad(12); // close to a top-down route map
    this.controls.maxPolarAngle = THREE.MathUtils.degToRad(86); // down to an almost eye-level profile
    this.controls.minAzimuthAngle = -Math.PI / 2; // swing a quarter turn to either side
    this.controls.maxAzimuthAngle = Math.PI / 2;
    this.renderer.domElement.addEventListener("dblclick", () =>
      this.resetView(),
    );
    // ----x-----x-----x------x----------x------x-------x--------x----x-----x-----x------x----------x------x-------x--------x

    this.cars = [];
    this.carsReady = false;
    this.shadows = [];
    this.stops = [];
    this.labels = [];
    this.shadowTex = this._makeShadowTexture();
    this._m = new THREE.Matrix4(); // scratch for the framing math
    this._basis = new THREE.Matrix4(); // scratch for orienting a car to the track tangent
    this._up = new THREE.Vector3(0, 1, 0);
    this._v = new THREE.Vector3();
    this._v2 = new THREE.Vector3();
    this._proj = new THREE.Vector3(); // scratch for projecting label anchors, reused every frame

    this._resizePending = false;
    this._resize();
    window.addEventListener("resize", () => this._queueResize());
  }

  // coalesce a burst of resize events into one reflow per animation frame
  _queueResize() {
    if (this._resizePending) return;
    this._resizePending = true;
    requestAnimationFrame(() => {
      this._resizePending = false;
      this._resize();
    });
  }

  setRoute(route, labelsContainer) {
    this.labelsContainer = labelsContainer;
    this.route = route;
    this.needleEl = this.container.querySelector(".compass .needle");

    this._buildTransform(route);
    this.curve = this._buildCurve(route);
    this._buildCarPath(); // a smoothed travel path so cars run straight while the ribbon stays real

    this._addRibbon();
    this._buildStops(route);
    this._frame();
  }

  // Cars travel on their own smoothed path, separate from the ribbon. The ribbon follows the real
  // route exactly, but a car tracking every GPS kink looks like it's swerving. The real curve is
  // sampled evenly by arc length, the Spadina Crescent jog is straightened, and a light moving
  // average removes the small lakeshore wobble while keeping the big shape — the lake corner and
  // the bend into Union — intact. frame() reads position and heading off this path.
  _buildCarPath() {
    const N = 600;
    const pts = [];
    for (let k = 0; k <= N; k++) pts.push(this.curve.getPointAt(k / N));
    this._straightenCarSpan(
      pts,
      N,
      this._stopS("willcocks"),
      this._stopS("college"),
    );
    this.carPts = this._smooth(pts, 6);
    this.carN = N;
  }

  _stopS(key) {
    const st = this.route.stops.find((s) => s.key === key);
    return st ? st.s : null;
  }

  // replace the car path between two arc-length fractions with a straight chord
  _straightenCarSpan(pts, N, s0, s1) {
    if (s0 == null || s1 == null) return;
    const i0 = Math.round(s0 * N),
      i1 = Math.round(s1 * N);
    if (i1 <= i0) return;
    const a = pts[i0],
      b = pts[i1];
    for (let i = i0 + 1; i < i1; i++) {
      const f = (i - i0) / (i1 - i0);
      pts[i] = new THREE.Vector3(
        a.x + (b.x - a.x) * f,
        0,
        a.z + (b.z - a.z) * f,
      );
    }
  }

  // a clamped moving average over the sampled points, so the terminals stay anchored where they are
  _smooth(pts, w) {
    const out = [];
    for (let i = 0; i < pts.length; i++) {
      let sx = 0,
        sz = 0,
        c = 0;
      for (let j = -w; j <= w; j++) {
        const k = i + j;
        if (k < 0 || k >= pts.length) continue;
        sx += pts[k].x;
        sz += pts[k].z;
        c++;
      }
      out.push(new THREE.Vector3(sx / c, 0, sz / c));
    }
    return out;
  }

  // Rotates the raw geometry so the Spadina leg points straight right, then scales and centres it.
  // Everything else (ribbon, stops, cars) is built off this rotated, fitted curve so the
  // projection lives in exactly one place.
  _buildTransform(route) {
    const a = route.stops[0]; // Spadina Station
    const b =
      route.stops.find((s) => s.key === "king") ||
      route.stops[Math.floor(route.stops.length * 0.45)];
    this.phi = -Math.atan2(b.y - a.y, b.x - a.x); // send the Spadina leg onto +x
    const c = Math.cos(this.phi),
      s = Math.sin(this.phi);
    this._rot = (x, y) => [x * c - y * s, x * s + y * c];
    // north is +y in the source projection; carry that direction through the same rotation and
    // the z flip so the compass can point to true north no matter how the route is turned.
    this.northWorld = new THREE.Vector3(-s, 0, -c).normalize();

    let rxMin = Infinity,
      rxMax = -Infinity,
      ryMin = Infinity,
      ryMax = -Infinity;
    for (const [x, y] of route.path) {
      const [rx, ry] = this._rot(x, y);
      rxMin = Math.min(rxMin, rx);
      rxMax = Math.max(rxMax, rx);
      ryMin = Math.min(ryMin, ry);
      ryMax = Math.max(ryMax, ry);
    }
    this.scale = FIT_W / (rxMax - rxMin);
    this.cx = (rxMin + rxMax) / 2;
    this.cy = (ryMin + ryMax) / 2;
  }

  // Maps (x,y) in [0,1] to a point on the ground plane. Cross axis goes to -z so the lake
  // end of the line recedes toward the top of the frame.
  _toWorld(x, y) {
    const [rx, ry] = this._rot(x, y);
    return new THREE.Vector3(
      (rx - this.cx) * this.scale,
      0,
      -(ry - this.cy) * this.scale,
    );
  }

  // Subsamples the dense polyline then fits a centripetal Catmull-Rom through it, smoothing
  // block-by-block GPS jitter into clean curves while keeping the real shape.
  _buildCurve(route) {
    const pts = [];
    const step = 5;
    for (let i = 0; i < route.path.length; i += step) {
      const [x, y] = route.path[i];
      pts.push(this._toWorld(x, y));
    }
    const [lx, ly] = route.path[route.path.length - 1];
    pts.push(this._toWorld(lx, ly));
    return new THREE.CatmullRomCurve3(pts, false, "centripetal");
  }

  // Right-of-way: a flat ribbon following the curve, with a thin centreline on top.
  // Built as a triangle strip by offsetting each sampled point along the in-plane normal.
  _addRibbon() {
    this.scene.add(this._ribbonMesh(ROW_HALF, 0.0, ROW));
    this.scene.add(this._ribbonMesh(ROW_HALF * 0.06, 0.02, RAIL));
  }

  _ribbonMesh(halfWidth, y, color) {
    const seg = 320;
    const pos = [];
    const idx = [];
    for (let i = 0; i <= seg; i++) {
      const u = i / seg;
      const p = this.curve.getPointAt(u);
      const t = this.curve.getTangentAt(u);
      const nx = -t.z,
        nz = t.x; // perpendicular to the tangent, in the ground plane
      const len = Math.hypot(nx, nz) || 1;
      const ox = (nx / len) * halfWidth,
        oz = (nz / len) * halfWidth;
      pos.push(p.x + ox, y, p.z + oz);
      pos.push(p.x - ox, y, p.z - oz);
      if (i < seg) {
        const k = i * 2;
        idx.push(k, k + 1, k + 2, k + 1, k + 3, k + 2);
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.setIndex(idx);
    return new THREE.Mesh(
      g,
      new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide }),
    );
  }

  // Every stop is a flush disc on the band. Majors are inked and ringed; everyday stops are
  // small and quiet; stops I'd consolidate are open red rings that fade in the proposal view.
  // Each stop carries a floating name; the collision pass in _updateLabels keeps them legible.
  // Name heights are staggered so neighbours on the straight Spadina leg clear each other.
  _buildStops(route) {
    route.stops.forEach((st, i) => {
      const major = MAJORS.has(st.key);
      // sit Union where the cars actually stop, short of the terminal loop, not at the loop's tip
      const placeS = st.key === "union" ? UNION_STOP_S : st.s;
      const p = this.curve.getPointAt(Math.min(Math.max(placeS, 0), 1));

      let disc;
      if (st.remove) {
        disc = new THREE.Mesh(
          new THREE.RingGeometry(4.5, 7, 32),
          new THREE.MeshBasicMaterial({
            color: TODAY,
            transparent: true,
            opacity: 0.95,
            side: THREE.DoubleSide,
          }),
        );
      } else {
        disc = new THREE.Mesh(
          new THREE.CircleGeometry(major ? 6.5 : 4, 32),
          new THREE.MeshBasicMaterial({ color: major ? INK : MUTED }),
        );
      }
      disc.rotation.x = -Math.PI / 2;
      disc.position.set(p.x, 0.06, p.z);
      this.scene.add(disc);

      if (major) {
        const ring = new THREE.Mesh(
          new THREE.RingGeometry(8.5, 10, 32),
          new THREE.MeshBasicMaterial({
            color: INK,
            transparent: true,
            opacity: 0.5,
            side: THREE.DoubleSide,
          }),
        );
        ring.rotation.x = -Math.PI / 2;
        ring.position.set(p.x, 0.04, p.z);
        this.scene.add(ring);
      }

      const entry = { st, disc, tick: null };
      if (major || st.remove) {
        const stemTop = major ? 58 : 40;
        const tick = new THREE.Mesh(
          new THREE.BoxGeometry(2.2, stemTop, 2.2),
          new THREE.MeshBasicMaterial({
            color: st.remove ? TODAY : MUTED,
            transparent: true,
            opacity: st.remove ? 0.85 : 0.5,
          }),
        );
        tick.position.set(p.x, stemTop / 2, p.z);
        this.scene.add(tick);
        entry.tick = tick;
      }
      this.stops.push(entry);

      const anchorH = (major ? 70 : 40) + (i % 2) * 30;
      const el = document.createElement("div");
      el.className =
        "lbl" + (major ? " major" : "") + (st.remove ? " removed" : "");
      el.textContent = st.name;
      this.labelsContainer.appendChild(el);
      this.labels.push({
        st,
        el,
        major,
        priority: major ? 2 : st.remove ? 1 : 0,
        world: new THREE.Vector3(p.x, anchorH, p.z),
        w: 0,
        h: 0,
      });
    });
  }

  setData(sim) {
    this.sim = sim;
    this.runIndex = 0;

    // size the pools to the busiest run in either scenario, since each loop swaps in a different
    // run with its own number of cars
    let most = 0;
    for (const key of ["today", "proposed"]) {
      for (const run of sim.scenarios[key].runs) {
        if (run.vehicles.length > most) most = run.vehicles.length;
      }
    }

    // one soft blob shadow per car, oriented to its heading each frame
    for (let i = 0; i < most; i++) {
      const shadow = new THREE.Mesh(
        new THREE.PlaneGeometry(1, 1),
        new THREE.MeshBasicMaterial({
          map: this.shadowTex,
          transparent: true,
          opacity: 0.32,
          depthWrite: false,
        }),
      );
      shadow.visible = false;
      this.scene.add(shadow);
      this.shadows.push(shadow);
    }

    this._loadCars(most);
  }

  // Loads the Flexity model once, normalises it to a template centred on the track with wheels
  // on the ground, then clones it for every car in the pool. Clones share geometry and materials
  // so the whole fleet stays light despite being real 3D. Each frame, frame() assigns every car
  // its position, heading and screen-locked scale.
  _loadCars(count) {
    new GLTFLoader().load(
      MODEL_URL,
      (gltf) => {
        const inner = gltf.scene;
        const box = new THREE.Box3().setFromObject(inner);
        const c = box.getCenter(new THREE.Vector3());
        // re-origin so the wrapping group sits with its length centre over the track and its
        // wheels on y = 0; the group itself is what I position, rotate and scale per frame
        inner.position.set(-c.x, -box.min.y, -c.z);
        this.carBaseLen = box.max.x - box.min.x;
        this.carWidth = box.max.z - box.min.z;

        const template = new THREE.Group();
        template.add(inner);

        for (let i = 0; i < count; i++) {
          const car = template.clone(true);
          car.visible = false;
          this.scene.add(car);
          this.cars.push(car);
        }
        this.carsReady = true;
      },
      undefined,
      // if the model 404s or the network drops, the cars would silently never appear; log it so
      // the failure is at least visible in the console rather than a mystery
      (err) => console.error("Could not load the streetcar model:", err),
    );
  }

  setRun(i) {
    this.runIndex = i;
  }

  setMode(key) {
    this.scenarioKey = key;
    const proposed = key === "proposed";
    for (const s of this.stops) {
      if (!s.st.remove) continue;
      s.disc.material.opacity = proposed ? 0.0 : 0.95;
      if (s.tick) s.tick.material.opacity = proposed ? 0.0 : 0.85;
    }
    for (const l of this.labels) {
      if (l.st.remove) l.el.classList.toggle("gone", proposed);
    }
  }

  frame(timeSec) {
    const runs = this.sim.scenarios[this.scenarioKey].runs;
    const vehicles = runs[this.runIndex % runs.length].vehicles;

    if (this.carsReady) {
      const worldLen = this._carWorldLen();
      const scale = worldLen / this.carBaseLen; // model is ~31.8 long; screen-lock that to TRAM_PX
      const footW = this.carWidth * scale;

      for (let i = 0; i < this.cars.length; i++) {
        const car = this.cars[i];
        const shadow = this.shadows[i];
        const veh = vehicles[i];
        const s = veh ? this._sAtTime(veh.keys, timeSec) : null;
        // hide a car once it has reached Union, so it pulls in and vanishes rather than driving the
        // tight terminal loop and appearing to spin around at the end of the line
        if (s === null || s > UNION_STOP_S) {
          car.visible = false;
          shadow.visible = false;
          continue;
        }
        // position and heading come from the smoothed car path, not the ribbon, so cars run straight
        // through the crescent and the lakeshore even though the ribbon keeps its real shape
        const ss = Math.min(Math.max(s, 0), 1);
        const idx = ss * this.carN;
        const i0 = Math.min(Math.floor(idx), this.carN - 1);
        const f = idx - i0;
        const a = this.carPts[i0];
        const b = this.carPts[i0 + 1];
        const px = a.x + (b.x - a.x) * f;
        const pz = a.z + (b.z - a.z) * f;
        const ahead = this.carPts[Math.min(i0 + 4, this.carN)];
        const behind = this.carPts[Math.max(i0 - 4, 0)];

        // face the car down the smoothed tangent, keep it upright, and screen-lock its length
        const fwd = this._v
          .set(
            (ahead.x - behind.x) * NOSE_SIGN,
            0,
            (ahead.z - behind.z) * NOSE_SIGN,
          )
          .normalize();
        const side = this._v2.set(-fwd.z, 0, fwd.x); // fwd x up, completes a right-handed basis
        this._basis.makeBasis(fwd, this._up, side);
        car.quaternion.setFromRotationMatrix(this._basis);
        car.position.set(px, 0, pz);
        car.scale.setScalar(scale);
        car.visible = true;

        // a soft blob shadow under the car, elongated along its heading so it tracks every turn
        const acrossUp = this._v2.set(fwd.z, 0, -fwd.x); // pairs with up so the plane faces the sky
        this._basis.makeBasis(fwd, acrossUp, this._up);
        shadow.quaternion.setFromRotationMatrix(this._basis);
        shadow.position.set(px, 0.05, pz);
        shadow.scale.set(worldLen * 0.95, footW * 2.2, 1);
        shadow.visible = true;
      }
    }

    this.controls.update();
    this.renderer.render(this.scene, this.camera);
    this._updateLabels();
    this._updateCompass();
  }

  // Points the compass needle at true north by projecting the origin and a northward step into
  // screen space, so the arrow stays correct even as the camera rotates.
  _updateCompass() {
    if (!this.needleEl) return;
    const o = this._v.set(0, 0, 0).project(this.camera);
    const n = this._v2
      .copy(this.northWorld)
      .multiplyScalar(200)
      .project(this.camera);
    const deg = (Math.atan2(n.x - o.x, n.y - o.y) * 180) / Math.PI;
    this.needleEl.style.transform = `rotate(${deg}deg)`;
  }

  // World length of a car, sized to read as TRAM_PX pixels at the default (zoom = 1) framing.
  // Deliberately not divided by live zoom, so the car keeps a fixed world size: it grows as the
  // reader zooms in and shrinks as they pull back, rather than being pinned to one pixel size.
  // The frustum height (top - bottom) doesn't change with zoom on an orthographic camera, so
  // this value only changes when the panel is resized.
  _carWorldLen() {
    return (
      (TRAM_PX * (this.camera.top - this.camera.bottom)) /
      (this.container.clientHeight || 1)
    );
  }

  _sAtTime(keys, t) {
    if (t < keys[0][0] || t > keys[keys.length - 1][0]) return null;
    let lo = 0,
      hi = keys.length - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (keys[mid][0] <= t) lo = mid;
      else hi = mid;
    }
    const [t0, s0] = keys[lo];
    const [t1, s1] = keys[hi];
    const f = t1 === t0 ? 0 : (t - t0) / (t1 - t0);
    return s0 + (s1 - s0) * f;
  }

  _makeShadowTexture() {
    const s = 128;
    const c = document.createElement("canvas");
    c.width = c.height = s;
    const ctx = c.getContext("2d");
    const g = ctx.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
    g.addColorStop(0, "rgba(40,34,26,0.5)");
    g.addColorStop(0.5, "rgba(40,34,26,0.2)");
    g.addColorStop(1, "rgba(40,34,26,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, s, s);
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  }

  // Fit the whole route in the frame, then tilt the camera down. The orbit limits set in the
  // constructor keep the reader inside a frame that always works.
  _frame() {
    this.controls.target.set(0, 0, 0);
    const dist = 3000;
    this.camera.position.set(0, Math.sin(TILT) * dist, Math.cos(TILT) * dist);
    this.camera.lookAt(0, 0, 0);
    this._resize();
    this.controls.update();
  }

  // double-click handler: snap zoom, pan and angle back to the editorial overview after exploring
  resetView() {
    this.camera.zoom = 1;
    this._frame();
  }

  _updateLabels() {
    const w = this.container.clientWidth;
    const h = this.container.clientHeight;

    const items = [];
    for (const l of this.labels) {
      if (l.el.classList.contains("gone")) {
        l.el.style.display = "none";
        continue;
      }
      if (!l.w) {
        l.w = l.el.offsetWidth;
        l.h = l.el.offsetHeight;
      }
      const p = this._proj.copy(l.world).project(this.camera);
      const onScreen =
        p.z < 1 && p.x > -1.15 && p.x < 1.15 && p.y > -1.15 && p.y < 1.15;
      if (!onScreen) {
        l.el.style.display = "none";
        continue;
      }
      l.sx = (p.x * 0.5 + 0.5) * w;
      l.sy = (-p.y * 0.5 + 0.5) * h;
      items.push(l);
    }

    // greedy declutter: place the important names first (majors, then the drops), and hide or
    // nudge any later name whose box would overlap one already placed.
    items.sort((a, b) => b.priority - a.priority || a.sx - b.sx);
    const placed = [];
    const pad = 3;
    for (const l of items) {
      let top = l.sy - l.h; // the label sits above its anchor
      let box = this._box(l, top);
      if (this._hits(box, placed, pad)) {
        top -= l.h + 6; // try one row higher
        box = this._box(l, top);
      }
      if (this._hits(box, placed, pad)) {
        l.el.style.display = "none";
        continue;
      }
      l.el.style.display = "block";
      l.el.style.left = l.sx + "px";
      l.el.style.top = top + l.h + "px"; // translate(-50%, -100%) lifts it to `top`
      placed.push(box);
    }
  }

  _box(l, top) {
    return { x0: l.sx - l.w / 2, x1: l.sx + l.w / 2, y0: top, y1: top + l.h };
  }

  _hits(b, placed, pad) {
    for (const p of placed) {
      if (
        b.x0 - pad < p.x1 &&
        b.x1 + pad > p.x0 &&
        b.y0 - pad < p.y1 &&
        b.y1 + pad > p.y0
      )
        return true;
    }
    return false;
  }

  resize() {
    this._resize();
  }

  _resize() {
    const w = this.container.clientWidth;
    const h = this.container.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h);
    if (this.curve) this._applyFit();
    else {
      const a = w / h;
      this.camera.left = -500 * a;
      this.camera.right = 500 * a;
      this.camera.top = 500;
      this.camera.bottom = -500;
      this.camera.updateProjectionMatrix();
    }
  }

  // Frames the route and its labels exactly by projecting every must-stay-on-screen point into
  // the tilted camera's view plane, computing that bounding box, and sizing the orthographic
  // frustum to it for the current panel shape. The route fills the height; on a wide panel the
  // leftover is horizontal, filled by the full-bleed ground colour with no empty white margin.
  _applyFit() {
    const w = this.container.clientWidth,
      h = this.container.clientHeight;
    this.camera.updateMatrixWorld();
    const inv = this._m.copy(this.camera.matrixWorld).invert();
    const v = this._v;
    let minX = Infinity,
      maxX = -Infinity,
      minY = Infinity,
      maxY = -Infinity;
    for (const p of this._contentPoints()) {
      v.copy(p).applyMatrix4(inv);
      if (v.x < minX) minX = v.x;
      if (v.x > maxX) maxX = v.x;
      if (v.y < minY) minY = v.y;
      if (v.y > maxY) maxY = v.y;
    }
    const mx = (maxX - minX) * 0.035,
      my = (maxY - minY) * 0.07;
    minX -= mx;
    maxX += mx;
    minY -= my;
    maxY += my;
    let cw = maxX - minX,
      ch = maxY - minY;
    const cx = (minX + maxX) / 2,
      cy = (minY + maxY) / 2;
    const aspect = w / h;
    if (cw / ch < aspect) cw = ch * aspect;
    else ch = cw / aspect;

    this.frustumH = ch;
    this.camera.left = cx - cw / 2;
    this.camera.right = cx + cw / 2;
    this.camera.top = cy + ch / 2;
    this.camera.bottom = cy - ch / 2;
    this.camera.updateProjectionMatrix();
  }

  // the points whose on-screen positions must stay framed: a sweep along the route plus every
  // floating name, so the labels above the Union hook never clip.
  _contentPoints() {
    const pts = [];
    for (let i = 0; i <= 24; i++) pts.push(this.curve.getPointAt(i / 24));
    for (const l of this.labels) pts.push(l.world);
    return pts;
  }
}
