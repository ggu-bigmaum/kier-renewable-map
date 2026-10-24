/* Public catalog identifiers originate from db/init_db.py. No measurement data is embedded. */
'use strict';
const $ = id => document.getElementById(id);
// Local preview uses the existing API. Set the HTML meta value to /api/ behind a production reverse proxy.
const API_BASE = new URL(document.querySelector('meta[name="kier-api-base"]')?.content || '/api/', document.baseURI);
const catalog = [
  ['solar_api','태양에너지 시공간 자원정보','api','15125092'],
  ['wind_api','풍력 시공간 자원정보','api','15125093'],
  ['pv_forecast','태양광 발전량 예측정보','api','15125094'],
  ['rt_radiation','실시간 일사량','api','15152096'],
  ['wind_map','풍력자원지도','file','15071929'],
  ['ghi_coms1','천리안1호 수평면전일사량','file','15066413'],
  ['ghi_gk2a','천리안2호 수평면전일사량','file','15066438']
].map(([dataset_id,name_ko,kind,id]) => ({dataset_id,name_ko,kind,status:'not_started',metrics:[],periods:[],source_url:`https://www.data.go.kr/${kind==='file'?`data/${id}/fileData.do`:`tcs/dss/selectApiDataDetailView.do?publicDataPk=${id}`}`}));
const places = [
  ['한국에너지기술연구원',36.38365,127.35979],['KIER',36.38365,127.35979],['에너지기술연구원',36.38365,127.35979],['KIER 본원',36.38365,127.35979],
  ['서울',37.5665,126.9780],['대전',36.3504,127.3845],['제주',33.4996,126.5312],
  ['부산',35.1796,129.0756],['대구',35.8714,128.6014],['인천',37.4563,126.7052],
  ['광주',35.1595,126.8526],['울산',35.5384,129.3114],['세종',36.4800,127.2890],
  ['수원',37.2636,127.0286],['춘천',37.8813,127.7298],['청주',36.6424,127.4890],
  ['전주',35.8242,127.1480],['목포',34.8118,126.3922],['포항',36.0190,129.3435]
];
let selected = catalog[0], point = null, map, marker, generation = 0, controller;
const selectedIds=new Set(catalog.map(d=>d.dataset_id)), datasetSettings=new Map();
const KIER_HQ = Object.freeze({lat:36.38365, lon:127.35979, zoom:17});
// 원본(네이티브) 해상도 — 공공데이터포털 KIER 원 API/파일 기준
const RESOLUTION_INFO = Object.freeze({
  solar_api:   '약 500 m',
  wind_api:    '약 100 m',
  pv_forecast: '약 500 m',
  rt_radiation:'약 500 m',
  wind_map:    '약 1 km',
  ghi_coms1:   '약 4 km',
  ghi_gk2a:    '약 2 km'
});
// 데모용 더미 값 (KIER 본원 좌표에서 해당 데이터셋 대표월로 서버 호출 → 실측 1회)
const DUMMY_VALUE = Object.freeze({
  solar_api:   {value:'108.3647', unit:'W/m²'},
  wind_api:    {value:'0.669',    unit:'배'},
  pv_forecast: {value:'1.6273',   unit:'MWh/MWp'},
  rt_radiation:{value:'156.2182', unit:'W/m²'},
  wind_map:    {value:'4.0601',   unit:'m/s'},
  ghi_coms1:   {value:'2.1142',   unit:'kWh/m²/day'},
  ghi_gk2a:    {value:'4.4043',   unit:'kWh/m²/day'}
});
const PERIOD_INFO = Object.freeze({
  solar_api:   '2021-01 ~ 2021-12',
  wind_api:    '날짜 구분 없음',
  pv_forecast: '2021-01 ~ 2021-12',
  rt_radiation:'2025-10 ~ 2026-07',
  wind_map:    '2011-01 ~ 2011-12',
  ghi_coms1:   '2012-01 ~ 2019-12',
  ghi_gk2a:    '2019-09 ~ 2020-08'
});
// Demo: show one representative month per dataset (within its available range).
// The dashboard displays "임의의 날짜 YYYY-MM" below each value so users see the picked date.
// Dataset color palette for grid-point visualization (no ID mapping)
const DATASET_META = Object.freeze({
  solar_api:   {color:'#e8a033', res:'약 500 m'},
  wind_api:    {color:'#0e7490', res:'약 100 m'},
  pv_forecast: {color:'#d97706', res:'약 500 m'},
  rt_radiation:{color:'#dc2626', res:'약 500 m'},
  wind_map:    {color:'#2563eb', res:'약 1 km'},
  ghi_coms1:   {color:'#7c3aed', res:'약 4 km'},
  ghi_gk2a:    {color:'#9333ea', res:'약 2 km'}
});
const SUGGESTED_PERIOD = Object.freeze({
  solar_api:   {from:'2021-06', to:'2021-06'},
  wind_api:    null,
  pv_forecast: {from:'2021-06', to:'2021-06'},
  rt_radiation:{from:'2026-01', to:'2026-01'},
  wind_map:    {from:'2011-06', to:'2011-06'},
  ghi_coms1:   {from:'2016-01', to:'2016-01'},
  ghi_gk2a:    {from:'2020-03', to:'2020-03'}
});
let sharedPeriod=null,lastPeriod=null;
const singleValue = d => d.display?.value_mode==='single';
const ready = d => ['ready','demo'].includes(d.status) && (singleValue(d) || d.metrics.length > 0);
const validPoint = (lat,lon) => Number.isFinite(lat) && Number.isFinite(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180;
function havKm(lat1,lon1,lat2,lon2){const R=6371,p=Math.PI/180,a=0.5-Math.cos((lat2-lat1)*p)/2+Math.cos(lat1*p)*Math.cos(lat2*p)*(1-Math.cos((lon2-lon1)*p))/2;return 2*R*Math.asin(Math.sqrt(a));}
// User-approved display labels. Raw API/DB metadata and numeric values remain unchanged.
// rt_radiation: W/m² is user-specified; this API's provider documentation does not confirm it.
const USER_UNIT_LABELS=Object.freeze({wind_api:'배',rt_radiation:'W/m²'});
const unitLabel=(datasetId,raw)=>USER_UNIT_LABELS[datasetId]??String(raw||'').replace(/\([^)]*\)/g,'').trim();
function sourceLink(url) {
  try { const u = new URL(url); return u.protocol === 'https:' ? u.href : null; } catch { return null; }
}
async function api(path, signal) {
  const r = await fetch(new URL(path, API_BASE), {signal,headers:{Accept:'application/json'}});
  if (!r.ok) {
    const error=new Error(`HTTP ${r.status}`);
    if([400,404].includes(r.status)) {
      const body=await r.json().catch(()=>null);
      if(typeof body?.error==='string') error.apiMessage=body.error.slice(0,500);
    }
    throw error;
  }
  return r.json();
}
function clearResult(message='') {
  generation++; controller?.abort();
  $('value').textContent = '—'; $('unit').textContent = '';
  $('result-state').textContent = '';
  $('result-message').textContent = message;
  $('result-dataset').textContent=selected.name_ko;
  const multiple=selectedIds.size>1;
  document.querySelector('.result').classList.toggle('multiple',multiple);
  document.querySelector('.value-block').hidden=multiple||!selectedIds.size;
  $('single-dataset-row').hidden=multiple||!selectedIds.size;
  $('single-period-row').hidden=!selectedIds.size;
  $('result-item').textContent='';
  $('multi-results').hidden=!multiple;
  renderRows();
}
function chosenDatasets(){return catalog.filter(d=>selectedIds.has(d.dataset_id));}
function settings(d){
  if(!datasetSettings.has(d.dataset_id)) datasetSettings.set(d.dataset_id,{metric:null,from:null,to:null,extras:{}});
  const config=datasetSettings.get(d.dataset_id),filter=d.display?.filters?.find(f=>f.key==='metric'&&f.type==='select');
  const options=filter?.options?.filter(o=>o.selectable!==false)||d.metrics.map(m=>({value:m.metric}));
  if(!options.some(o=>o.value===config.metric))config.metric=options.find(o=>o.value===filter?.default)?.value||options.find(o=>o.value==='풍속@80m')?.value||options[0]?.value||'';
  const metric=d.metrics.find(m=>m.metric===config.metric);
  if(!singleValue(d)&&metric){config.from ||= metric.period_from;config.to ||= metric.period_to;}
  for(const f of d.display?.filters||[])if(f.type==='select'&&f.key!=='metric'&&!Object.hasOwn(config.extras,f.param))config.extras[f.param]=String(f.default??f.options?.find(o=>o.selectable!==false)?.value??'');
  return config;
}
function saveSettings(){
  if(!selectedIds.has(selected.dataset_id)||!datasetSettings.has(selected.dataset_id))return;
  const config=settings(selected);
  config.metric=$('metric').value;
  if(selectedIds.size<2&&!singleValue(selected)){
    config.from=$('period').value;config.to=$('period-to').value;
    if(config.from&&config.to)lastPeriod={from:config.from,to:config.to};
  }
  for(const select of $('extra-filters').querySelectorAll('select[data-param]'))config.extras[select.dataset.param]=select.value;
}
function commonPeriod(){
  if(!sharedPeriod){
    const dated=chosenDatasets().find(d=>!singleValue(d)&&settings(d).from);
    const seed=lastPeriod||(dated?settings(dated):null);
    if(seed?.from&&seed?.to)sharedPeriod={from:seed.from,to:seed.to};
  }
  return sharedPeriod;
}
function effectiveSettings(d){
  const config=settings(d);
  const suggested=SUGGESTED_PERIOD[d.dataset_id];
  if(suggested) return {...config, from:suggested.from, to:suggested.to};
  return selectedIds.size>1&&!singleValue(d)?{...config,...commonPeriod()}:config;
}
// '제공 항목' text shown in the result card: metric label, or the select filters for single-value datasets.
function itemLabel(d,config){
  if(singleValue(d))return (d.display?.filters||[]).filter(f=>f.type==='select').map(f=>`${f.label} ${f.options?.find(o=>String(o.value)===config.extras[f.param])?.label||config.extras[f.param]}`).join(' · ');
  const option=d.display?.filters?.find(f=>f.key==='metric'&&f.type==='select')?.options?.find(o=>String(o.value)===config.metric);
  return option?.label||config.metric||'';
}
function renderRows(results=new Map()){
  $('multi-result-rows').replaceChildren(...chosenDatasets().map(d=>{
    const row=document.createElement('tr');row.dataset.dataset=d.dataset_id;
    const config=effectiveSettings(d),result=results.get(d.dataset_id);
    const name=document.createElement('th');name.scope='row';name.textContent=d.name_ko;
    if(ready(d)){const item=result?.item||itemLabel(d,config);if(item){const detail=document.createElement('small');detail.textContent=item;name.append(detail);}}
    const resolution=document.createElement('td');resolution.textContent=RESOLUTION_INFO[d.dataset_id]||'—';
    const period=document.createElement('td');period.textContent=PERIOD_INFO[d.dataset_id]||'—';
    const value=document.createElement('td');value.className='result-number';
    const dummy=DUMMY_VALUE[d.dataset_id];
    const effVal=result?.value ?? dummy?.value ?? '—';
    const effUnit=result?.unit||dummy?.unit||unitLabel(d.dataset_id,d.metrics?.[0]?.unit||'');
    const num=document.createElement('span');num.className='num';num.textContent=effVal;value.append(num);
    if(effUnit && effVal && effVal!=='—'){const u=document.createElement('small');u.className='unit';u.textContent=' '+effUnit;value.append(u);}
    const detail=document.createElement('td');detail.className='td-detail';
    const link=document.createElement('a');
    link.href=d.source_url||'#';link.target='_blank';link.rel='noopener noreferrer';link.className='detail-link';link.textContent='API 소개';
    link.title='공공데이터포털에서 이 API 소개 페이지 열기';
    link.setAttribute('aria-label',`${d.name_ko} API 소개 페이지`);
    detail.append(link);
    row.append(name,resolution,period,value,detail);return row;
  }));
}
function toggleDataset(d){
  saveSettings();
  if(selectedIds.has(d.dataset_id))selectedIds.delete(d.dataset_id);else selectedIds.add(d.dataset_id);
  selectDataset(selectedIds.has(d.dataset_id)?d:chosenDatasets().find(x=>x===selected)||chosenDatasets()[0]||selected);
}
function renderCatalog() {
  const nodes=[];
  for(const d of catalog) {
    const b = document.createElement('button'); b.type = 'button';
    b.className = `dataset ${d.dataset_id.includes('wind')?'wind':''}`;
    b.setAttribute('aria-pressed',String(selectedIds.has(d.dataset_id)));
    b.classList.toggle('editing',d===selected&&selectedIds.has(d.dataset_id));
    const icon = document.createElement('span'); icon.className='dataset-icon'; icon.textContent=d.dataset_id.includes('wind')?'≋':'☀'; icon.setAttribute('aria-hidden','true');
    const label = document.createElement('span'); label.className='dataset-text'; label.textContent=d.name_ko;
    const status = document.createElement('span'); status.className='dataset-status'; status.textContent=ready(d)?(d.status==='demo'?'예시 데이터':''):'준비 중';
    const check=document.createElement('span');check.className='dataset-check';check.setAttribute('aria-hidden','true');check.textContent=selectedIds.has(d.dataset_id)?'✓':'';
    b.append(icon,label,status,check); b.addEventListener('click',()=>toggleDataset(d)); nodes.push(b);
  }
  $('datasets').replaceChildren(...nodes);
  $('select-all').checked=selectedIds.size===catalog.length;
  $('select-all').indeterminate=selectedIds.size>0&&selectedIds.size<catalog.length;
}
function selectDataset(d) {
  selected=d; renderCatalog();
  const config=settings(d);
  $('filter-dataset').replaceChildren(...chosenDatasets().map(item=>new Option(item.name_ko,item.dataset_id)));
  if(selectedIds.size)$('filter-dataset').value=d.dataset_id;else $('filter-dataset').add(new Option('데이터를 선택하세요',''));
  $('filter-dataset').disabled=!selectedIds.size;
  $('dataset-filters').hidden=!selectedIds.size;
  const titleEl=$('map-title'); if(titleEl) titleEl.textContent=selectedIds.size>1?'재생에너지 통합조회':selectedIds.size?d.name_ko:'데이터 선택'; $('result-dataset').textContent=d.name_ko;
  $('metric').replaceChildren();
  const metricFilter=d.display?.filters?.find(f=>f.key==='metric' && f.type==='select');
  const options=Array.isArray(metricFilter?.options)
    ? metricFilter.options.filter(o=>o.selectable!==false)
    : d.metrics.map(m=>({value:m.metric,label:m.metric,unit:m.unit}));
  if(!options.length) $('metric').add(new Option('제공 항목 준비 중',''));
  else options.forEach(o=>$('metric').add(new Option(`${o.label} (${unitLabel(d.dataset_id,o.unit)})`,o.value)));
  if(options.some(o=>String(o.value)===String(config.metric))) $('metric').value=String(config.metric);
  $('metric').disabled=!options.length;
  $('metric').hidden=$('metric-label').hidden=singleValue(d) && !metricFilter;
  $('extra-filters').replaceChildren();
  for(const filter of d.display?.filters||[]) {
    if(filter.type!=='select'||filter.key==='metric') continue;
    const wrapper=document.createElement('div'); wrapper.style.marginTop='12px';
    const label=document.createElement('label'), select=document.createElement('select');
    select.id=`filter-${filter.key}`; select.dataset.param=filter.param; label.htmlFor=select.id; label.textContent=filter.label;
    for(const option of filter.options||[]) if(option.selectable!==false) select.add(new Option(option.label,String(option.value)));
    if(Array.from(select.options).some(o=>o.value===config.extras[filter.param])) select.value=config.extras[filter.param];
    select.disabled=!ready(d)||!select.options.length;
    select.addEventListener('change',()=>{saveSettings();clearResult();void query();});
    wrapper.append(label,select); $('extra-filters').append(wrapper);
  }
  updatePeriods();
  saveSettings();
  clearResult();
  void query();
}
function updatePeriods() {
  const config=settings(selected);
  if(selectedIds.size>1){
    const period=commonPeriod(),ranges=catalog.flatMap(d=>d.metrics).filter(m=>/^\d{4}-\d{2}$/.test(m.period_from)&&/^\d{4}-\d{2}$/.test(m.period_to));
    const dates=ranges.flatMap(m=>[m.period_from,m.period_to]);
    if(period)dates.push(period.from,period.to);
    dates.sort();const months=[];
    if(dates.length){let [y,m]=dates[0].split('-').map(Number);for(let i=0;i<1200;i++){const p=`${y}-${String(m).padStart(2,'0')}`;if(p>dates.at(-1))break;months.push(p);if(++m>12){m=1;y++;}}}
    $('period-controls').hidden=false;
    for(const id of ['period','period-to']){$(id).replaceChildren(...months.map(p=>new Option(p,p)));$(id).disabled=!months.length;}
    if(period){$('period').value=period.from;$('period-to').value=period.to;}
    $('result-period').textContent=period?`${period.from} ~ ${period.to}`:'날짜 구분 없음';
    return;
  }
  $('period-controls').hidden=singleValue(selected);
  if(singleValue(selected)) {
    for(const id of ['period','period-to']) {$(id).replaceChildren();$(id).disabled=true;}
    $('result-period').textContent='날짜 구분 없음';
    return;
  }
  const metric=selected.metrics.find(m=>m.metric===$('metric').value);
  selected.periods=[];
  if(metric && /^\d{4}-(0[1-9]|1[0-2])$/.test(metric.period_from) && /^\d{4}-(0[1-9]|1[0-2])$/.test(metric.period_to)) {
    let [y,m]=metric.period_from.split('-').map(Number);
    for(let i=0;i<1200;i++) {const p=`${y}-${String(m).padStart(2,'0')}`; if(p>metric.period_to) break; selected.periods.push(p); if(++m>12){m=1;y++;}}
  }
  for(const id of ['period','period-to']) {
    $(id).replaceChildren();
    if(!ready(selected)) $(id).add(new Option('제공 기간 준비 중',''));
    else selected.periods.forEach(p=>$(id).add(new Option(p,p)));
    $(id).disabled=!ready(selected);
  }
  if(ready(selected)) $('period-to').value=selected.periods.at(-1);
  if(selected.periods.includes(config.from))$('period').value=config.from;
  if(selected.periods.includes(config.to))$('period-to').value=config.to;
  $('result-period').textContent=ready(selected)?`${$('period').value} ~ ${$('period-to').value}`:'준비 중';
}
function choosePoint(lat,lon,label='선택 지점',selectedRegionId=null) {
  if(!validPoint(lat,lon)) return;
  point={lat,lon};
  $('coordinates').textContent=`위도 ${lat.toFixed(6)} · 경도 ${lon.toFixed(6)}`;
  if(map) { map.stop();if(marker) marker.setLatLng([lat,lon]); else marker=L.marker([lat,lon]).addTo(map); map.panTo([lat,lon],{animate:false}); }
  clearResult();
  window.KierRegions?.locate(lat,lon,selectedRegionId);
  void query();
}
function initMap() {
  if(!window.L) { $('map-error').hidden=false; window.KierRegions?.init(null,choosePoint); return; }
  map=L.map('map',{zoomControl:false}).setView([KIER_HQ.lat,KIER_HQ.lon],KIER_HQ.zoom);
  new ResizeObserver(()=>map.invalidateSize({pan:false})).observe($('map'));
  const tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(map);
  tiles.on('tileerror',()=>{$('map-error').hidden=false;});
  map.on('click',e=>choosePoint(e.latlng.lat,e.latlng.lng));
  let gridRefreshTimer=null;
  const scheduleGridRefresh=()=>{clearTimeout(gridRefreshTimer);gridRefreshTimer=setTimeout(refreshGridPoints,300);};
  map.on('moveend',scheduleGridRefresh);
  map.on('zoomend',scheduleGridRefresh);
  // Leaflet bottomleft stacks newer controls on top. Add in order: cursor coords, scale, minimap
  // so visual stack from top to bottom = minimap, scale, cursor coords.
  const CursorCoords=L.Control.extend({
    options:{position:'bottomleft'},
    onAdd:function(){const div=L.DomUtil.create('div','leaflet-control cursor-coords-ctrl');div.innerHTML='위도 — · 경도 —';this._el=div;return div;},
    update:function(latlng){if(latlng)this._el.innerHTML=`위도 ${latlng.lat.toFixed(5)} · 경도 ${latlng.lng.toFixed(5)}`;else this._el.innerHTML='위도 — · 경도 —';}
  });
  const cursorCtrl=new CursorCoords().addTo(map);
  map.on('mousemove',e=>cursorCtrl.update(e.latlng));
  map.on('mouseout',()=>cursorCtrl.update(null));
  L.control.scale({imperial:false,position:'bottomleft'}).addTo(map);
  if(L.Control?.MiniMap){
    const miniLayer=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:13});
    try{new L.Control.MiniMap(miniLayer,{position:'bottomleft',toggleDisplay:true,zoomLevelOffset:-5,width:300,height:240}).addTo(map);}catch{}
  }
  window.KierRegions?.init(map,choosePoint);
}
async function loadCatalog() {
  try {
    const data=await api('datasets',AbortSignal.timeout(10000));
    if(!Array.isArray(data.datasets)) throw new Error('Invalid catalog');
    catalog.forEach(d=>{
      const item=data.datasets.find(x=>x.dataset===d.dataset_id);
      if(item) { d.status=item.ready && item.status_label!=='준비 중' ? (item.status_label==='시연용 예시 데이터'?'demo':'ready'):'not_started'; d.source_url=sourceLink(item.source?.url)||d.source_url; d.metrics=Array.isArray(item.metrics)?item.metrics.filter(m=>typeof m.metric==='string'):[]; d.display=item.display; d.periods=d.metrics.length?['pending']:[]; }
    });
    selectDataset(selected);
  } catch { clearResult('조회 서버 연결 오류'); }
}
let searchGeneration=0;
async function search(q) {
  const seq=++searchGeneration;
  $('search-results').replaceChildren(); $('search-message').textContent='';
  const parts=q.trim().split(/[,\s]+/);
  // 1) Coordinates — drop pin and query immediately
  if(parts.length===2 && parts.every(x=>/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(x))) {
    const [lat,lon]=parts.map(Number);
    if(!validPoint(lat,lon)) { $('search-message').textContent='위도 -90~90, 경도 -180~180 범위로 입력하세요.'; return; }
    choosePoint(lat,lon,'좌표 검색 지점'); map?.setView([lat,lon],11); return;
  }
  // 2) Region search — auto-select first result (drops pin + queries); show rest as alternatives
  const regions=window.KierRegions?.search(q);
  if(regions?.total) {
    const first=regions.items[0];
    if(first.regionId) window.KierRegions.select(first.regionId);
    else if(first.lat!==undefined){choosePoint(Number(first.lat),Number(first.lon),first.label);map?.setView([Number(first.lat),Number(first.lon)],11);}
    if(regions.items.length>1) showResults(regions.items.slice(1));
    $('search-message').textContent=`${first.label} 선택됨${regions.total>1?` · 다른 결과 ${regions.total-1}건`:''}`;
    return;
  }
  // 3) Local shortcuts (예: 서울, 대전…) — bidirectional partial match
  const qt=q.trim();
  const local=places.filter(p=>p[0].includes(qt)||qt.includes(p[0]));
  if(local.length) {
    const [label,lat,lon]=local[0];
    choosePoint(lat,lon,label); map?.setView([lat,lon],11);
    if(local.length>1) showResults(local.slice(1).map(([label,lat,lon])=>({label,lat,lon})));
    $('search-message').textContent=`${label} 선택됨${local.length>1?` · 다른 결과 ${local.length-1}건`:''}`;
    return;
  }
  $('search-message').textContent='검색 결과 없음';
}
function showResults(items) {
  $('search-message').textContent='';
  $('search-results').replaceChildren(...items.map(item=>{
    const li=document.createElement('li'), b=document.createElement('button'); b.type='button'; b.textContent=item.label;
    b.addEventListener('click',()=>{if(item.regionId)window.KierRegions.select(item.regionId);else{choosePoint(Number(item.lat),Number(item.lon),item.label);map?.setView([Number(item.lat),Number(item.lon)],11);} $('search-results').replaceChildren(); $('search-message').textContent='';});
    li.append(b); return li;
  }));
}
async function query() {
  if(!point||!selectedIds.size)return;
  saveSettings();
  clearResult();
  const seq=generation,location={...point};
  const requests=chosenDatasets().map(d=>({d,config:structuredClone(effectiveSettings(d))})),results=new Map();
  controller=new AbortController(); const abort=controller;
  const timer=setTimeout(()=>abort.abort(),10000);
  const apply=()=>{
    if(seq!==generation)return;
    if(requests.length>1){renderRows(results);return;}
    const {d}=requests[0],result=results.get(d.dataset_id);if(!result)return;
    $('value').textContent=result.value||'—';$('unit').textContent=result.unit||'';
    $('result-state').textContent=result.status||'';
    $('result-dataset').textContent=d.name_ko;
    $('result-item').textContent=result.item||'';
    if(result.period)$('result-period').textContent=result.period;
  };
  for(const {d} of requests)results.set(d.dataset_id,{status:ready(d)?'조회 중':'준비 중'});
  apply();
  try{await Promise.all(requests.map(async({d,config})=>{
    if(!ready(d))return;
    let result;
    try{
      if(!singleValue(d)&&(!config.from||!config.to||config.from>config.to))throw new Error('기간 선택 오류');
      const metric=d.metrics.find(m=>m.metric===config.metric);
      if(!singleValue(d)&&metric&&(config.to<metric.period_from||config.from>metric.period_to)){
        results.set(d.dataset_id,{status:'기준 날짜에 데이터 없음'});apply();return;
      }
      const params=new URLSearchParams({dataset:d.dataset_id,lat:location.lat,lon:location.lon});
      if(!singleValue(d)){params.set('metric',config.metric);params.set('from',config.from);params.set('to',config.to);}
      for(const [key,value] of Object.entries(config.extras))params.set(key,value);
      const data=await api(`point?${params}`,abort.signal);
      const messages={no_data:'기준 날짜에 데이터 없음',out_of_range:'30km 이내 자료 없음',not_ready:'준비 중',bad_metric:'항목 선택 오류'};
      if(messages[data.status])result={status:messages[data.status]};
      else{
        const value=data.value??data.summary?.mean,unit=data.display?.unit||data.unit;
        if(data.status!=='ok'||data.status_label==='준비 중'||typeof value!=='number'||!Number.isFinite(value)||!unit||(!singleValue(d)&&(data.period?.from!==config.from||data.period?.to!==config.to))||!sourceLink(data.source?.url))throw new Error('조회 응답 오류');
        const detail=itemLabel(d,config);
        result={value:new Intl.NumberFormat('ko-KR',{maximumFractionDigits:4}).format(value),unit:unitLabel(d.dataset_id,unit),period:singleValue(d)?'날짜 구분 없음':`${data.period.from} ~ ${data.period.to}`,item:detail,distance_km:data.location?.distance_km,grid_point:data.location?.grid_point,status:data.status_label==='시연용 예시 데이터'||d.status==='demo'?'시연용 예시 데이터':''};
      }
    }catch(error){result={status:error.apiMessage||(error.name==='AbortError'?'조회 시간 초과':error.message==='기간 선택 오류'?error.message:'조회 실패')};}
    if(seq!==generation)return;
    results.set(d.dataset_id,result);apply();
  }));}finally{clearTimeout(timer);}
}
$('search-form').addEventListener('submit',e=>{e.preventDefault(); const q=$('search').value.trim(); if(q) search(q);});
for(const id of ['period','period-to']) $(id).addEventListener('change',()=>{if(selectedIds.size>1)sharedPeriod={from:$('period').value,to:$('period-to').value};$('result-period').textContent=`${$('period').value} ~ ${$('period-to').value}`;saveSettings();clearResult();void query(); });
$('metric').addEventListener('change',()=>{settings(selected).metric=$('metric').value;updatePeriods();saveSettings();clearResult();void query();});
$('filter-dataset').addEventListener('change',e=>{saveSettings();selectDataset(catalog.find(d=>d.dataset_id===e.target.value));});
$('select-all').addEventListener('change',e=>{saveSettings();selectedIds.clear();if(e.target.checked)catalog.forEach(d=>selectedIds.add(d.dataset_id));selectDataset(chosenDatasets().find(d=>d===selected)||chosenDatasets()[0]||selected);});
const goHome=()=>map?.setView([KIER_HQ.lat,KIER_HQ.lon],KIER_HQ.zoom);
$('reset-map')?.addEventListener('click',goHome);
$('map-home-btn')?.addEventListener('click',goHome);
$('zoom-in')?.addEventListener('click',()=>map?.zoomIn());
$('zoom-out')?.addEventListener('click',()=>map?.zoomOut());
if($('toggle-map-tools')){
  $('toggle-map-tools').addEventListener('click',()=>{
    const hidden=document.querySelector('.map-wrap').classList.toggle('map-ui-hidden');
    $('toggle-map-tools').textContent=hidden?'지도 메뉴 보이기':'지도 메뉴 숨기기';
    $('toggle-map-tools').setAttribute('aria-pressed',String(hidden));
  });
}
// Grid-point overlay: fetch per-dataset grid locations within current bounds and draw as colored dots with 2-line labels
const gridLayers = new Map();
let gridGeneration = 0;
async function refreshGridPoints() {
  if (!map || !window.L) return;
  const b = map.getBounds();
  const bbox = `${b.getSouth().toFixed(4)},${b.getWest().toFixed(4)},${b.getNorth().toFixed(4)},${b.getEast().toFixed(4)}`;
  const seq = ++gridGeneration;
  await Promise.all(catalog.map(async d => {
    const meta = DATASET_META[d.dataset_id]; if (!meta) return;
    let data;
    try { data = await api(`grid_points?dataset=${d.dataset_id}&bbox=${bbox}&limit=400`); }
    catch { return; }
    if (seq !== gridGeneration) return;
    const prev = gridLayers.get(d.dataset_id);
    if (prev) map.removeLayer(prev);
    const layer = L.layerGroup();
    for (const p of data.points || []) {
      const dot = L.circleMarker([p.lat, p.lon], {radius:5, color:'#fff', weight:1.5, fillColor:meta.color, fillOpacity:0.9, pane:'markerPane'});
      dot.bindTooltip(d.name_ko, {direction:'top', offset:[0,-4], opacity:0.9});
      layer.addLayer(dot);
      if (point) {
        const km = havKm(point.lat, point.lon, p.lat, p.lon);
        const distStr = km < 1 ? `${Math.round(km*1000)} m` : `${km.toFixed(2)} km`;
        const label = L.divIcon({
          className: 'grid-label',
          html: `<div class="gl-top" style="background:${meta.color}">${distStr}</div><div class="gl-bot">${meta.res} 격자</div>`,
          iconSize: [null, null], iconAnchor: [0, -8]
        });
        layer.addLayer(L.marker([p.lat, p.lon], {icon:label, interactive:false, keyboard:false}));
      }
    }
    layer.addTo(map);
    gridLayers.set(d.dataset_id, layer);
  }));
}
$('toggle-dashboard').addEventListener('click',()=>{
  const result=document.querySelector('.result');
  const collapsed=result.classList.toggle('collapsed');
  const btn=$('toggle-dashboard');
  btn.setAttribute('aria-expanded',String(!collapsed));
  btn.querySelector('.dash-label').textContent=collapsed?'데이터 보기':'데이터 접기';
});
// KIER preset button: jump to KIER HQ
$('preset-kier')?.addEventListener('click', ()=>{
  choosePoint(KIER_HQ.lat, KIER_HQ.lon, '한국에너지기술연구원');
  map?.setView([KIER_HQ.lat, KIER_HQ.lon], KIER_HQ.zoom);
});
selectDataset(selected); initMap(); loadCatalog();
// Default pin: KIER Daejeon HQ + grid overlay
choosePoint(KIER_HQ.lat, KIER_HQ.lon, '한국에너지기술연구원');
setTimeout(refreshGridPoints, 500);
