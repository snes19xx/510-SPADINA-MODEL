// 2.5D diorama of the 510 Spadina route.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const CARD = 0xf0ebe0; // the ground the route sits on
const ROW = 0xe4dac4; // the right-of-way
const RAIL = 0xc7b89a; // the centreline
const INK = 0xb63333;
const MUTED = 0x9c9384;
const TODAY = 0x981616; // TTC red

const TRAM_PX = 105; // on-screen length of a car

const MODEL_URL = "assets/streetcar.glb"; // the merged Flexity Outlook
const NOSE_SIGN = 2;

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

export class Diorama {
  constructor(container) {
    this.container = container;
    this.scenarioKey = "today";

    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setClearColor(CARD, 1); // full bleed, no white margins
    container.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();

    // Bright hemisphere keeps the red roof from blowing out.
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0xe7dfce, 3.0));
    const key = new THREE.DirectionalLight(0xffffff, 1.1);
    key.position.set(-0.3, 0.7, 1.0); // low and front, keeps the roof colour
    this.scene.add(key);

    // Ortho keeps equal distances equal on screen, which a distance-true corridor needs.
    this.camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 500, 6000);
    this.frustumH = 900;

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.enablePan = true;
    this.controls.screenSpacePanning = true;
    this.controls.zoomToCursor = true;
    this.controls.minZoom = 0.7;
    this.controls.maxZoom = 12.0;
    this.controls.minPolarAngle = THREE.MathUtils.degToRad(12); // near top-down
    this.controls.maxPolarAngle = THREE.MathUtils.degToRad(86); // near eye-level
    this.controls.minAzimuthAngle = -Math.PI / 2; // a quarter turn each way
    this.controls.maxAzimuthAngle = Math.PI / 2;
    this.renderer.domElement.addEventListener("dblclick", () =>
      this.resetView(),
    );

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
    this._proj = new THREE.Vector3(); // scratch for label anchors

    this._resizePending = false;
    this._resize();
    window.addEventListener("resize", () => this._queueResize());
  }

  // one reflow per animation frame
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
    this._buildCarPath();

    this._addRibbon();
    this._buildStops(route);
    this._frame();
  }

  // Cars run on their own smoothed path so they do not swerve on GPS kinks; the ribbon
  // keeps the real geometry.
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

  // clamped at the ends so the terminals stay anchored
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

  // Rotate the Spadina leg onto +x, then scale and centre. Everything else builds off this.
  _buildTransform(route) {
    const a = route.stops[0]; // Spadina Station
    const b =
      route.stops.find((s) => s.key === "king") ||
      route.stops[Math.floor(route.stops.length * 0.45)];
    this.phi = -Math.atan2(b.y - a.y, b.x - a.x); // send the Spadina leg onto +x
    const c = Math.cos(this.phi),
      s = Math.sin(this.phi);
    this._rot = (x, y) => [x * c - y * s, x * s + y * c];
    // carry north through the same rotation and z flip, for the compass
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

  // Cross axis goes to -z so the lake end recedes.
  _toWorld(x, y) {
    const [rx, ry] = this._rot(x, y);
    return new THREE.Vector3(
      (rx - this.cx) * this.scale,
      0,
      -(ry - this.cy) * this.scale,
    );
  }

  // Centripetal Catmull-Rom over a subsampled polyline, smoothing GPS jitter.
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

  // Triangle strip, offset along the in-plane normal.
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

  // Name heights stagger so neighbours on the straight Spadina leg clear each other.
  _buildStops(route) {
    route.stops.forEach((st, i) => {
      const major = MAJORS.has(st.key);
      // Union sits where cars stop, short of the loop tip
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

    // size the pools to the busiest run in either scenario
    let most = 0;
    for (const key of ["today", "proposed"]) {
      for (const run of sim.scenarios[key].runs) {
        if (run.vehicles.length > most) most = run.vehicles.length;
      }
    }

    // one blob shadow per car
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

  // Load once, then clone per car. Clones share geometry and materials.
  _loadCars(count) {
    new GLTFLoader().setMeshoptDecoder(MeshoptDecoder).load(
      MODEL_URL,
      (gltf) => {
        const inner = gltf.scene;

        // No normals in the file; flatShading is required or the cars render black.
        inner.traverse((o) => {
          if (!o.isMesh) return;
          for (const m of Array.isArray(o.material)
            ? o.material
            : [o.material]) {
            m.flatShading = true;
          }
        });

        const box = new THREE.Box3().setFromObject(inner);
        const c = box.getCenter(new THREE.Vector3());
        // centre on length, wheels at y = 0
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
        // hide at Union, short of the terminal loop
        if (s === null || s > UNION_STOP_S) {
          car.visible = false;
          shadow.visible = false;
          continue;
        }
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

        // blob shadow, elongated along the heading
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

  // Project a northward step into screen space so the needle tracks camera rotation.
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

  // World length for TRAM_PX at zoom 1. Live zoom is deliberately excluded, so a car
  // keeps a fixed world size and grows as the reader zooms in.
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

  _frame() {
    this.controls.target.set(0, 0, 0);
    const dist = 3000;
    this.camera.position.set(0, Math.sin(TILT) * dist, Math.cos(TILT) * dist);
    this.camera.lookAt(0, 0, 0);
    this._resize();
    this.controls.update();
  }

  // snap back to the overview
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

    // majors and drops are placed first; later names nudge up or hide
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

  // Size the ortho frustum to the projected bounds of everything that must stay framed.
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

  // route sweep plus every label anchor
  _contentPoints() {
    const pts = [];
    for (let i = 0; i <= 24; i++) pts.push(this.curve.getPointAt(i / 24));
    for (const l of this.labels) pts.push(l.world);
    return pts;
  }
}
