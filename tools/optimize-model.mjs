// Builds assets/streetcar.glb from the raw Flexity export.
//
//   git show 8f88af1:assets/streetcar.glb > streetcar.src.glb
//   npm install @gltf-transform/core @gltf-transform/extensions \
//               @gltf-transform/functions meshoptimizer sharp
//   node tools/optimize-model.mjs streetcar.src.glb assets/streetcar.glb

import { NodeIO } from "@gltf-transform/core";
import { ALL_EXTENSIONS } from "@gltf-transform/extensions";
import {
  dedup,
  flatten,
  join,
  meshopt,
  palette,
  prune,
  simplify,
  textureCompress,
  weld,
} from "@gltf-transform/functions";
import { MeshoptEncoder, MeshoptSimplifier } from "meshoptimizer";
import sharp from "sharp";

const SRC = process.argv[2];
const DST = process.argv[3];

const RATIO = 0.5;
const ERROR = 0.01;

await MeshoptSimplifier.ready;
await MeshoptEncoder.ready;

const io = new NodeIO()
  .registerExtensions(ALL_EXTENSIONS)
  .registerDependencies({ "meshopt.encoder": MeshoptEncoder });
const doc = await io.read(SRC);

function dropNormals(document) {
  for (const mesh of document.getRoot().listMeshes()) {
    for (const prim of mesh.listPrimitives()) {
      const normal = prim.getAttribute("NORMAL");
      const index = prim.getIndices();
      if (!normal) continue;
      for (let i = 0; i < index.getCount(); i += 3) {
        const [a, b, c] = [
          index.getScalar(i),
          index.getScalar(i + 1),
          index.getScalar(i + 2),
        ];
        const [na, nb, nc] = [a, b, c].map((v) =>
          normal.getElement(v, [0, 0, 0]),
        );
        const spread = Math.max(
          ...na.map((v, k) => Math.abs(v - nb[k]) + Math.abs(v - nc[k])),
        );
        if (spread > 1e-4) {
          throw new Error(
            "Model has smooth-shaded triangles; dropping NORMAL would change how it " +
              "looks. Remove dropNormals here and flatShading in scene.js.",
          );
        }
      }
      prim.setAttribute("NORMAL", null);
    }
  }
}

await doc.transform(
  dedup(),
  flatten(),
  prune({ keepAttributes: false, keepLeaves: false }),

  textureCompress({
    encoder: sharp,
    targetFormat: "webp",
    resize: [256, 256],
    slots: /baseColor/,
  }),

  palette({ min: 2 }),
  join({ keepNamed: false }),

  dropNormals,
  weld(),
  simplify({ simplifier: MeshoptSimplifier, ratio: RATIO, error: ERROR }),

  dedup(),
  prune({ keepAttributes: false, keepLeaves: false }),
  meshopt({ encoder: MeshoptEncoder, level: "high" }),
);

await io.write(DST, doc);

let prims = 0,
  tris = 0,
  verts = 0;
for (const mesh of doc.getRoot().listMeshes()) {
  for (const prim of mesh.listPrimitives()) {
    prims++;
    tris += prim.getIndices().getCount() / 3;
    verts += prim.getAttribute("POSITION").getCount();
  }
}
console.log(
  `${DST}: ${prims} primitives, ${tris} triangles, ${verts} vertices`,
);
