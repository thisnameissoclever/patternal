// Prove the viewport's sparse morph blending against a body small enough to
// check by hand.
//
// The basis stores one delta per source vertex, but the renderer holds a
// vertex per UV corner, so a source vertex that sits on a UV seam appears
// more than once and every copy has to move together. A basis that reached
// only the first copy would tear the body open exactly along its seams, which
// is the failure this guards.
//
// The functions are read out of avatar3d.html rather than copied, so this
// tests what ships.
//
//   node tools/test_avatar_sparse_morph_basis.mjs

import { readFileSync } from 'node:fs';
import { strict as assert } from 'node:assert';

const source = readFileSync(new URL('../Patternal/Assets/avatar3d.html', import.meta.url), 'utf8');

function extractFunction(name) {
  const start = source.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, `${name} is not present in avatar3d.html`);
  let depth = 0;
  let seenBody = false;
  for (let index = start; index < source.length; index++) {
    const character = source[index];
    if (character === '{') { depth++; seenBody = true; }
    else if (character === '}') {
      depth--;
      if (seenBody && depth === 0) return source.slice(start, index + 1);
    }
  }
  throw new Error(`${name} is not closed in avatar3d.html`);
}

const { buildSparseMorphBasis, addSparseMorphEndpoint } = new Function(
  `${extractFunction('buildSparseMorphBasis')}
   ${extractFunction('addSparseMorphEndpoint')}
   return { buildSparseMorphBasis, addSparseMorphEndpoint };`
)();

// Source vertex 1 is split across two UV islands, so it owns render vertices
// 1 and 3. Source vertices 0 and 2 own one render vertex each.
const bodyData = { sourceVertexIndices: [0, 1, 2, 1] };

// One parameter. Its minimum endpoint moves source vertices 0 and 1; its
// maximum endpoint moves source vertex 2 only.
const minimumIndices = Uint32Array.from([0, 1]);
const minimumDeltas = Float32Array.from([0.1, 0.2, 0.3, 1, 2, 3]);
const maximumIndices = Uint32Array.from([2]);
const maximumDeltas = Float32Array.from([-1, -2, -3]);

const parts = [minimumIndices, minimumDeltas, maximumIndices, maximumDeltas];
const total = parts.reduce((sum, part) => sum + part.byteLength, 0);
const buffer = new ArrayBuffer(total);
const bytes = new Uint8Array(buffer);
const offsets = [];
let cursor = 0;
for (const part of parts) {
  offsets.push(cursor);
  bytes.set(new Uint8Array(part.buffer, part.byteOffset, part.byteLength), cursor);
  cursor += part.byteLength;
}

const declaration = {
  sourceVertexCount: 3,
  baselineHeightCm: 167,
  parameters: [{
    avatarKey: 'probe',
    avatarSourceKeys: ['probe'],
    minimum: 0, baseline: 5, maximum: 10,
    endpoints: {
      minimum: { count: 2, indexByteOffset: offsets[0], deltaByteOffset: offsets[1] },
      maximum: { count: 1, indexByteOffset: offsets[2], deltaByteOffset: offsets[3] }
    }
  }]
};

const basis = buildSparseMorphBasis(declaration, buffer, bodyData);
assert.equal(basis.format, 'sparse-source-vertex');
assert.equal(basis.parameters.length, 1);

// Every render vertex of a source vertex must be listed under it.
const owned = (sourceVertex) =>
  Array.from(basis.renderVertices.slice(basis.starts[sourceVertex], basis.starts[sourceVertex + 1])).sort();
assert.deepEqual(owned(0), [0], 'source vertex 0 owns render vertex 0');
assert.deepEqual(owned(1), [1, 3], 'a seam vertex owns every render copy of itself');
assert.deepEqual(owned(2), [2], 'source vertex 2 owns render vertex 2');

// Blender metres reach render space as [x*2, z*2, y*2], so a delta of
// (0.1, 0.2, 0.3) at weight 1 must arrive as (0.2, 0.6, 0.4).
const body = { positions: new Float32Array(12) };
addSparseMorphEndpoint(basis, body, basis.parameters[0].minimumEndpoint, 1);
const near = (actual, expected, what) =>
  assert.ok(Math.abs(actual - expected) < 1e-6, `${what}: expected ${expected}, got ${actual}`);
near(body.positions[0], 0.2, 'render 0 x');
near(body.positions[1], 0.6, 'render 0 y takes the Blender z');
near(body.positions[2], 0.4, 'render 0 z takes the Blender y');
near(body.positions[3], 2, 'render 1 x');
near(body.positions[4], 6, 'render 1 y');
near(body.positions[5], 4, 'render 1 z');
near(body.positions[9], 2, 'the seam vertex second copy moved with the first');
near(body.positions[10], 6, 'the seam vertex second copy moved with the first');
near(body.positions[11], 4, 'the seam vertex second copy moved with the first');
near(body.positions[6], 0, 'an untouched vertex stayed put');

// Weight scales linearly, and a half weight is half the movement.
const half = { positions: new Float32Array(12) };
addSparseMorphEndpoint(basis, half, basis.parameters[0].maximumEndpoint, 0.5);
near(half.positions[6], -1, 'maximum endpoint x at half weight');
near(half.positions[7], -3, 'maximum endpoint y at half weight');
near(half.positions[8], -2, 'maximum endpoint z at half weight');
near(half.positions[0], 0, 'the minimum endpoint did not leak into the maximum');

// A basis that does not cover the body it is blended into must be refused
// rather than silently indexing past the end.
assert.throws(
  () => buildSparseMorphBasis(declaration, buffer, { sourceVertexIndices: [0, 1, 2, 9] }),
  /does not cover the display body/,
  'a body with more source vertices than the basis must be refused'
);

console.log('sparse morph basis: all checks passed');
