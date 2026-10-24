/* Administrative boundary UI: local, attributed data; no geocoder or DB access. */
(function() {
  'use strict';
  const $=id=>document.getElementById(id), geom=window.KierRegionGeometry;
  const BASE='data/boundaries/';
  let map,onSelect,index,provinces,districts,byId,baseLayer,townLayer,highlight;
  let initialized=false,selectGeneration=0,locateGeneration=0,drawGeneration=0,drawTimer;
  const files=new Map();
  async function json(file) {
    const response=await fetch(BASE+file,{signal:AbortSignal.timeout(15000)});
    if(!response.ok) throw new Error('Boundary HTTP '+response.status);
    return response.json();
  }
  function townFile(code) {
    if(!files.has(code)) files.set(code,json(`districts/${code}.geojson`).catch(error=>{files.delete(code);throw error;}));
    return files.get(code);
  }
  function options(element,items,placeholder) {
    element.replaceChildren(new Option(placeholder,''));
    items.forEach(r=>element.add(new Option(r.short||r.name,r.id)));
    element.disabled=!items.length;
  }
  function children(parent,level) {return index.regions.filter(r=>r.parent===parent&&r.level===level).sort((a,b)=>a.name.localeCompare(b.name,'ko'));}
  function sync(region) {
    const town=region.level==='town'?region:null;
    const district=town?byId.get(town.parent):region.level==='district'?region:null;
    const province=byId.get(district?district.parent:region.id);
    $('region-province').value=province.id;
    options($('region-district'),children(province.id,'district'),'시군구 전체');
    $('region-district').value=district?.id||'';
    options($('region-town'),district?children(district.id,'town'):[],'읍면동 전체');
    $('region-town').value=town?.id||'';
  }
  function style(level) {
    return {color:level==='town'?'#5d7ca4':'#247864',weight:level==='province'?2:1.3,fillColor:'#44866b',fillOpacity:0,bubblingMouseEvents:false};
  }
  function layer(features,level) {
    return L.geoJSON(features,{renderer:L.canvas({padding:.3}),style:()=>style(level),onEachFeature:(f,l)=>{
      l.on('click',e=>onSelect(e.latlng.lat,e.latlng.lng,f.properties.name+' · 지도 선택'));
    }});
  }
  async function featureFor(region) {
    const list=region.level==='province'?provinces.features:region.level==='district'?districts.features:(await townFile(region.parent)).features;
    return list.find(f=>f.properties.id===region.id);
  }
  async function select(id) {
    if(!initialized) return;
    const region=byId.get(id);if(!region)return;
    const seq=++selectGeneration;
    sync(region);$('region-status').textContent='불러오는 중…';
    try {
      const f=await featureFor(region);if(seq!==selectGeneration)return;
      if(!f)throw new Error('Missing region');
      if(map) {
        if(highlight)map.removeLayer(highlight);
        highlight=L.geoJSON(f,{interactive:false,style:()=>style(region.level,true)}).addTo(map);
        map.fitBounds([[region.bbox[1],region.bbox[0]],[region.bbox[3],region.bbox[2]]],{padding:[24,24],maxZoom:region.level==='town'?14:region.level==='district'?12:9});
      }
      $('region-status').textContent='';
      onSelect(region.lat,region.lon,region.name+' · 대표지점',region.id);
    } catch {$('region-status').textContent='경계 로딩 오류';}
  }
  function intersects(box,bounds) {return box[0]<=bounds.getEast()&&box[2]>=bounds.getWest()&&box[1]<=bounds.getNorth()&&box[3]>=bounds.getSouth();}
  async function draw() {
    if(!initialized||!map)return;
    const seq=++drawGeneration;
    $('boundary-error').hidden=true;
    if(baseLayer)map.removeLayer(baseLayer);
    if(townLayer)map.removeLayer(townLayer);
    if($('boundary-district').checked) {
      const showDistricts=map.getZoom()>=8;
      baseLayer=layer(showDistricts?districts:provinces,showDistricts?'district':'province').addTo(map);
    }
    if(!$('boundary-town').checked||map.getZoom()<11)return;
    const visible=districts.features.filter(f=>intersects(f.properties.bbox,map.getBounds()));
    if(visible.length>24)return;
    try {
      const data=await Promise.all(visible.map(f=>townFile(f.properties.id)));
      if(seq!==drawGeneration)return;
      townLayer=layer(data.flatMap(d=>d.features).filter(f=>intersects(f.properties.bbox,map.getBounds())),'town').addTo(map);
      highlight?.bringToFront();
    } catch {if(seq===drawGeneration){$('boundary-error').textContent='경계 로딩 오류';$('boundary-error').hidden=false;}}
  }
  async function locate(lat,lon,selectedRegionId=null) {
    if(!initialized)return;
    selectGeneration++;
    const seq=++locateGeneration;
    if(!selectedRegionId&&highlight){map?.removeLayer(highlight);highlight=null;}
    $('region-location').textContent='행정구역 확인 중…';
    try {
      const county=districts.features.find(f=>geom.inBox(f.properties.bbox,lat,lon)&&geom.contains(f.geometry,lat,lon));
      if(!county){$('region-location').textContent='일치하는 행정구역 없음';$('region-province').value='';options($('region-district'),[],'시군구 전체');options($('region-town'),[],'읍면동 전체');$('region-status').textContent='';return;}
      const data=await townFile(county.properties.id);if(seq!==locateGeneration)return;
      const town=data.features.find(f=>geom.inBox(f.properties.bbox,lat,lon)&&geom.contains(f.geometry,lat,lon));
      $('region-location').textContent=(town||county).properties.name;
      sync(town?town.properties:county.properties);
      if(!selectedRegionId) {
        const matched=town||county;
        if(map)highlight=L.geoJSON(matched,{interactive:false,style:()=>style(matched.properties.level,true)}).addTo(map);
        $('region-status').textContent='';
      }
    }catch {if(seq===locateGeneration)$('region-location').textContent='행정구역 확인 불가';}
  }
  function search(q) {
    if(!initialized)return null;
    const tokens=q.trim().toLowerCase().split(/\s+/);
    const matches=index.regions.filter(r=>tokens.every(t=>r.name.toLowerCase().includes(t)||r.id===t||r.stat_code===t));
    matches.sort((a,b)=>({province:0,district:1,town:2}[a.level]-{province:0,district:1,town:2}[b.level])||a.name.localeCompare(b.name,'ko'));
    return {total:matches.length,items:matches.slice(0,30).map(r=>({label:r.name,lat:r.lat,lon:r.lon,regionId:r.id}))};
  }
  async function init(theMap,selectPoint) {
    map=theMap;onSelect=selectPoint;
    $('region-status').textContent='불러오는 중…';
    $('region-retry').hidden=true;
    try {
      [index,provinces,districts]=await Promise.all([json('index.json'),json('provinces.geojson'),json('districts.geojson')]);
      byId=new Map(index.regions.map(r=>[r.id,r]));initialized=true;
      options($('region-province'),index.regions.filter(r=>r.level==='province').sort((a,b)=>a.name.localeCompare(b.name,'ko')),'시도 선택');
      $('region-status').textContent='';
      $('boundary-source').textContent='경계: SGIS · vuski/admdongkor (단순화) · 공공누리 1유형 · CC BY 4.0';
      $('boundary-source-link').href=index.metadata.source;
      if(map) {draw();map.on('moveend',()=>{clearTimeout(drawTimer);drawTimer=setTimeout(draw,180);});}
    }catch {$('region-status').textContent='경계 로딩 오류';$('region-retry').hidden=false;}
  }
  $('region-province')?.addEventListener('change',e=>{if(e.target.value)select(e.target.value);else{selectGeneration++;options($('region-district'),[],'시군구 전체');options($('region-town'),[],'읍면동 전체');if(highlight)map?.removeLayer(highlight);}});
  $('region-district')?.addEventListener('change',e=>select(e.target.value||$('region-province').value));
  $('region-town')?.addEventListener('change',e=>select(e.target.value||$('region-district').value));
  ['boundary-district','boundary-town'].forEach(id=>$(id)?.addEventListener('change',draw));
  $('region-retry')?.addEventListener('click',()=>init(map,onSelect));
  window.KierRegions={init,search,select,locate};
})();
