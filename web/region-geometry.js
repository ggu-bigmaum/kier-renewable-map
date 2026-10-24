/* Pure GeoJSON point tests. Outer rings include their boundary; holes are excluded. */
(function(root) {
  'use strict';
  function ringState(ring, x, y) {
    let inside=false;
    for(let i=0,j=ring.length-1;i<ring.length;j=i++) {
      const [ax,ay]=ring[j], [bx,by]=ring[i];
      const cross=(x-ax)*(by-ay)-(y-ay)*(bx-ax);
      if(Math.abs(cross)<1e-12 && x>=Math.min(ax,bx)-1e-12 && x<=Math.max(ax,bx)+1e-12 && y>=Math.min(ay,by)-1e-12 && y<=Math.max(ay,by)+1e-12) return 0;
      if((ay>y)!==(by>y) && x<(bx-ax)*(y-ay)/(by-ay)+ax) inside=!inside;
    }
    return inside?1:-1;
  }
  function polygonContains(rings,x,y) {
    return ringState(rings[0],x,y)>=0 && !rings.slice(1).some(r=>ringState(r,x,y)>=0);
  }
  function contains(geometry,lat,lon) {
    if(geometry.type==='Polygon') return polygonContains(geometry.coordinates,lon,lat);
    if(geometry.type==='MultiPolygon') return geometry.coordinates.some(r=>polygonContains(r,lon,lat));
    return false;
  }
  function inBox(b,lat,lon) {return lon>=b[0]&&lon<=b[2]&&lat>=b[1]&&lat<=b[3];}
  const api={contains,inBox};
  if(typeof module!=='undefined') module.exports=api;
  else root.KierRegionGeometry=api;
})(typeof window==='undefined'?globalThis:window);
