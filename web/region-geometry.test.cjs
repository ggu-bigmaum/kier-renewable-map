const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync,readdirSync}=require('node:fs');
const path=require('node:path');
const {contains,inBox}=require('./region-geometry.js');
test('Polygon holes, shared edges and separate islands',()=>{
 const p={type:'Polygon',coordinates:[[[0,0],[10,0],[10,10],[0,10],[0,0]],[[2,2],[4,2],[4,4],[2,4],[2,2]]]};
 assert.equal(contains(p,1,1),true);assert.equal(contains(p,3,3),false);assert.equal(contains(p,0,5),true);assert.equal(contains(p,11,5),false);
 const m={type:'MultiPolygon',coordinates:[p.coordinates,[[[20,20],[21,20],[21,21],[20,21],[20,20]]]]};
 assert.equal(contains(m,20.5,20.5),true);assert.equal(contains(m,15,15),false);
});
test('Every region has unique code, parent, bbox and a point inside its display polygon',()=>{
 const root=path.join(__dirname,'data/boundaries'),idx=JSON.parse(readFileSync(path.join(root,'index.json'))), ids=new Set();
 const all=[...JSON.parse(readFileSync(path.join(root,'provinces.geojson'))).features,...JSON.parse(readFileSync(path.join(root,'districts.geojson'))).features];
 for(const name of readdirSync(path.join(root,'districts')))all.push(...JSON.parse(readFileSync(path.join(root,'districts',name))).features);
 const byId=new Map(idx.regions.map(r=>[r.id,r]));
 const shapes=new Map(all.map(f=>[f.properties.id,f.geometry]));
 assert.equal(all.length,idx.regions.length);
 for(const f of all){const r=f.properties;assert.equal(ids.has(r.id),false,r.id);ids.add(r.id);if(r.parent){assert.ok(byId.has(r.parent),r.name);assert.ok(contains(shapes.get(r.parent),r.lat,r.lon),r.name+' parent contains representative point');}assert.ok(inBox(r.bbox,r.lat,r.lon),r.name);assert.ok(contains(f.geometry,r.lat,r.lon),r.name+' representative point');}
 assert.equal(idx.metadata.counts.towns,all.filter(f=>f.properties.level==='town').length);
});
