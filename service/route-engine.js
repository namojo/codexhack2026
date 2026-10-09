/* One deterministic routing engine for the local browser and Node checks. */
(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.RescueRouting = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const ASSUMED_WIDTHS = Object.freeze({trunk: 7, primary: 7, secondary: 6, tertiary: 5, residential: 3.2, unclassified: 3.2, living_street: 2.8, service: 2.8});
  const SPEED_KMH = 24;
  const TURN_MINUTES = 0.15;
  const ALLOWED_ACCESS = new Set(['yes', 'permissive', 'designated', 'destination']);
  const ALLOWED_BARRIERS = new Set(['no', 'entrance', 'toll_booth', 'cattle_grid']);
  const BAD_HIGHWAYS = new Set(['footway', 'path', 'pedestrian', 'steps', 'cycleway', 'construction', 'proposed', 'bridleway', 'corridor']);

  function meters(value) {
    if (typeof value === 'number') return Number.isFinite(value) && value > 0 ? value : null;
    if (typeof value !== 'string') return null;
    const v = value.trim().toLowerCase();
    let m = v.match(/^(\d+(?:\.\d+)?)\s*(m|metres|meters|cm|ft|feet)?$/);
    if (m) {
      const number = Number(m[1]);
      return number > 0 ? number * (m[2] === 'cm' ? .01 : ['ft', 'feet'].includes(m[2]) ? .3048 : 1) : null;
    }
    m = v.match(/^(\d+)\s*'\s*(\d+(?:\.\d+)?)\s*"$/);
    if (m && Number(m[2]) < 12) return Number(m[1]) * .3048 + Number(m[2]) * .0254 || null;
    return null;
  }

  class Heap {
    constructor() { this.items = []; }
    push(item) {
      let i = this.items.length;
      this.items.push(item);
      while (i > 0) {
        const p = (i - 1) >> 1;
        if (this.items[p].cost <= item.cost) break;
        this.items[i] = this.items[p]; i = p;
      }
      this.items[i] = item;
    }
    pop() {
      const first = this.items[0], last = this.items.pop();
      if (this.items.length) {
        let i = 0;
        while (i * 2 + 1 < this.items.length) {
          let c = i * 2 + 1;
          if (c + 1 < this.items.length && this.items[c + 1].cost < this.items[c].cost) c++;
          if (last.cost <= this.items[c].cost) break;
          this.items[i] = this.items[c]; i = c;
        }
        this.items[i] = last;
      }
      return first;
    }
  }

  function validate(network, input) {
    if (!network || !network.nodes || !Array.isArray(network.edges) || !network.origin || !Array.isArray(network.destinations)) throw Error('도로망 형식이 올바르지 않습니다.');
    if (!input || typeof input !== 'object' || Array.isArray(input)) throw Error('경로 입력 객체가 필요합니다.');
    const options = {destination_id: input.destination_id, vehicle_width_m: input.vehicle_width_m, vehicle_height_m: input.vehicle_height_m, clearance_m: input.clearance_m, mode: input.mode, closed_edge_ids: input.closed_edge_ids === undefined ? [] : input.closed_edge_ids};
    const ranges = [['vehicle_width_m', 1.5, 3.5, '차량 폭'], ['vehicle_height_m', 1.5, 4.5, '차량 높이'], ['clearance_m', .1, .8, '좌우 각각의 여유']];
    for (const [key, min, max, label] of ranges) if (typeof options[key] !== 'number' || !Number.isFinite(options[key]) || options[key] < min || options[key] > max) throw Error(`${label}는 ${min}~${max}m의 유한한 숫자로 입력하세요.`);
    if (!['training', 'strict'].includes(options.mode)) throw Error('계산 모드는 training 또는 strict여야 합니다.');
    const destination = network.destinations.find(d => d.id === options.destination_id);
    if (!destination || !network.nodes[destination.node_id] || !network.nodes[network.origin.node_id]) throw Error('출발점과 목적지의 도로 노드를 확인하세요.');
    const ids = new Set(network.edges.map(e => e.id));
    if (!Array.isArray(options.closed_edge_ids) || options.closed_edge_ids.some(id => typeof id !== 'string' || !ids.has(id))) throw Error('통제 목록에는 도로망에 있는 구간 ID만 입력하세요.');
    options.closed_edge_ids = [...new Set(options.closed_edge_ids)];
    return {options, destination};
  }

  function inspect(edge, options, recommended, closed) {
    const tags = edge.tags || {}, notes = [];
    if (closed.has(edge.id)) return {reason: 'closed'};
    if (BAD_HIGHWAYS.has(edge.highway || tags.highway)) return {reason: 'access'};
    // Every node restriction is retained in edge tags by the snapshot builder.
    for (const [key, value] of Object.entries(tags)) {
      const base = key.startsWith('node:') ? key.split(':').slice(2).join(':') : key;
      if (['access', 'vehicle', 'motor_vehicle', 'motorcar'].includes(base) && !ALLOWED_ACCESS.has(String(value).toLowerCase())) return {reason: 'access'};
      if (base === 'barrier' && !ALLOWED_BARRIERS.has(String(value).toLowerCase())) return {reason: 'barrier'};
      // Conditional/directional variants are unsupported; retain only numeric physical limits.
      if (/^(?:access|vehicle|motorcar|motor_vehicle|maxwidth|maxheight|width|maxweight|maxaxleload|maxlength|incline|barrier|oneway):/.test(base) && !['maxwidth:physical', 'maxheight:physical'].includes(base)) return {reason: 'unparsed_restriction'};
      if (base === 'maxwidth' || base === 'maxwidth:physical' || base === 'maxheight' || base === 'maxheight:physical') {
        const limit = meters(value);
        if (limit === null) return {reason: 'unparsed_restriction'};
        if (base.startsWith('maxwidth') && options.vehicle_width_m > limit) return {reason: 'maxwidth'};
        if (base.startsWith('maxheight') && options.vehicle_height_m > limit) return {reason: 'maxheight'};
      }
      if (['maxweight', 'maxaxleload', 'maxlength', 'incline'].includes(base)) notes.push(`${base}=${value}: 중량·차체길이·경사 조건은 계산하지 않았습니다.`);
      if (base === 'barrier' && value !== 'no') notes.push(`시설물 ${value}: 현장 통과 조건 확인 필요`);
      if (base === 'access' && value === 'destination') notes.push('목적지 접근 차량의 통행 조건 확인 필요');
    }
    if (!(typeof edge.length_m === 'number' && Number.isFinite(edge.length_m) && edge.length_m >= 0)) return {reason: 'invalid_edge'};
    const verified = Object.prototype.hasOwnProperty.call(tags, 'rescue:verified_width');
    const osmWidth = Object.prototype.hasOwnProperty.call(tags, 'width') ? meters(tags.width) : null;
    if (Object.prototype.hasOwnProperty.call(tags, 'width') && osmWidth === null) return {reason: 'unparsed_restriction'};
    let effective = verified ? meters(tags['rescue:verified_width']) : null;
    if (verified && effective === null) return {reason: 'unparsed_restriction'};
    let assumed = false;
    if (recommended) {
      if (!verified && options.mode === 'strict') return {reason: 'unknown_width'};
      if (!verified) {
        effective = ASSUMED_WIDTHS[(edge.highway || tags.highway || '').replace(/_link$/, '')];
        if (effective === undefined) return {reason: 'unknown_width'};
        assumed = true;
      }
      if (osmWidth !== null) effective = Math.min(effective, osmWidth);
      if (effective + 1e-9 < options.vehicle_width_m + 2 * options.clearance_m) return {reason: 'effective_width'};
    }
    return {effective_width_m: effective, verified, assumed, unknown: !verified, warnings: notes};
  }

  function isTurn(a, b) {
    if (!a) return false;
    const ag = a.geometry || [], bg = b.geometry || [];
    if (ag.length < 2 || bg.length < 2) return String(a.way_id) !== String(b.way_id);
    const end = ag[ag.length - 1], start = ag[ag.length - 2], next = bg[1], first = bg[0];
    const scale = Math.cos(end[1] * Math.PI / 180);
    const x1 = (end[0] - start[0]) * scale, y1 = end[1] - start[1];
    const x2 = (next[0] - first[0]) * scale, y2 = next[1] - first[1];
    const magnitude = Math.hypot(x1, y1) * Math.hypot(x2, y2);
    return magnitude > 0 && (x1 * x2 + y1 * y2) / magnitude < Math.cos(Math.PI / 6);
  }

  function turnAllowed(previous, edge, restrictions) {
    if (!previous) return true;
    const relevant = restrictions.get(`${previous.way_id}|${edge.from}`) || [];
    const only = relevant.filter(r => r.restriction.startsWith('only_'));
    if (only.length && !only.some(r => String(r.to_way) === String(edge.way_id) && (r.restriction === 'only_u_turn' ? String(edge.to) === String(previous.from) : String(edge.to) !== String(previous.from)))) return false;
    for (const r of relevant) {
      if (String(r.to_way) !== String(edge.way_id)) continue;
      if (r.restriction === 'no_u_turn') { if (String(edge.to) === String(previous.from)) return false; }
      else if (r.restriction === 'no_straight_on' && String(r.from_way) === String(r.to_way)) { if (String(edge.to) !== String(previous.from)) return false; }
      else if (r.restriction.startsWith('no_')) return false;
      else if (!r.restriction.startsWith('only_')) return false;
    }
    return true;
  }

  function routeSummary(edges, infos, network, options, recommended) {
    const nodeIds = [String(network.origin.node_id)], geometry = [], steps = [], warnings = new Set();
    let distance = 0, turns = 0, unknown = 0, assumed = 0;
    for (let i = 0; i < edges.length; i++) {
      const e = edges[i], info = infos.get(e.id), turn = isTurn(edges[i - 1], e);
      distance += e.length_m; turns += Number(turn); unknown += Number(info.unknown); assumed += Number(info.assumed);
      nodeIds.push(String(e.to));
      for (const point of e.geometry || []) {
        const last = geometry[geometry.length - 1];
        if (!last || last[0] !== point[0] || last[1] !== point[1]) geometry.push(point.slice());
      }
      for (const warning of info.warnings) warnings.add(warning);
      const name = e.name || '이름 없는 도로';
      let step = steps[steps.length - 1];
      if (!step || step.name !== name || turn) {
        step = {name, distance_m: 0, edge_ids: [], from_node_id: String(e.from), to_node_id: String(e.to), turn: i === 0 ? '출발' : turn ? '방향 전환' : '계속', highway: e.highway, effective_width_m: info.effective_width_m, assumed_width_count: 0, unknown_width_count: 0, warnings: []};
        steps.push(step);
      }
      step.distance_m += e.length_m; step.edge_ids.push(e.id); step.to_node_id = String(e.to);
      step.assumed_width_count += Number(info.assumed); step.unknown_width_count += Number(info.unknown);
      if (info.effective_width_m !== null) step.effective_width_m = step.effective_width_m === null ? info.effective_width_m : Math.min(step.effective_width_m, info.effective_width_m);
      step.warnings = [...new Set([...step.warnings, ...info.warnings])];
    }
    if (!edges.length) { const n = network.nodes[network.origin.node_id]; geometry.push([n.lon, n.lat]); }
    if (unknown) warnings.add(`현장 유효폭 미확인 구간 ${unknown}개${assumed ? `: 도로 등급별 훈련 가정 적용 ${assumed}개` : ''}`);
    if (!recommended) warnings.add('최단 비교: 차량 최대폭·높이 태그 제한은 적용하며 유효폭과 좌우 여유 필터는 제외합니다.');
    warnings.add('차체길이·회전반경·축중·경사·회차 공간과 현재 교통·침수·주차 상태는 검증하지 않았습니다.');
    for (const step of steps) step.distance_m = Math.round(step.distance_m * 100) / 100;
    return {edge_ids: edges.map(e => e.id), node_ids: nodeIds, distance_m: Math.round(distance * 100) / 100, estimated_minutes: Math.round((distance / (SPEED_KMH * 1000 / 60) + turns * TURN_MINUTES) * 100) / 100, turn_count: turns, unknown_width_count: unknown, assumed_width_count: assumed, steps, geometry, warnings: [...warnings]};
  }

  function solve(network, options, destination, recommended, restrictions) {
    const closed = new Set(options.closed_edge_ids), adjacency = new Map(), infos = new Map(), rejected = {closed: 0, access: 0, barrier: 0, maxwidth: 0, maxheight: 0, effective_width: 0, unknown_width: 0, unparsed_restriction: 0, invalid_edge: 0, turn_restriction: 0};
    for (const edge of network.edges) {
      const info = inspect(edge, options, recommended, closed);
      if (info.reason) { rejected[info.reason]++; continue; }
      infos.set(edge.id, info);
      const key = String(edge.from);
      if (!adjacency.has(key)) adjacency.set(key, []);
      adjacency.get(key).push(edge);
    }
    const heap = new Heap(), distances = new Map([['@origin', 0]]), parents = new Map(), edgeById = new Map(network.edges.map(e => [e.id, e]));
    heap.push({key: '@origin', node: String(network.origin.node_id), previous: null, cost: 0});
    let found = null;
    while (heap.items.length) {
      const state = heap.pop();
      if (state.cost !== distances.get(state.key)) continue;
      if (state.node === String(destination.node_id)) { found = state.key; break; }
      for (const edge of adjacency.get(state.node) || []) {
        if (!turnAllowed(state.previous, edge, restrictions)) { rejected.turn_restriction++; continue; }
        const info = infos.get(edge.id);
        let cost = edge.length_m;
        if (recommended) {
          const space = info.effective_width_m - options.vehicle_width_m - 2 * options.clearance_m;
          const narrow = space < .5 ? .3 : space < 1 ? .12 : 0;
          const minor = ['service', 'living_street'].includes(edge.highway) ? .16 : ['residential', 'unclassified'].includes(edge.highway) ? .06 : 0;
          cost *= 1 + narrow + minor + (info.unknown ? .06 : 0);
          if (isTurn(state.previous, edge)) cost += 25;
        }
        const total = state.cost + cost;
        if (!distances.has(edge.id) || total < distances.get(edge.id)) {
          distances.set(edge.id, total); parents.set(edge.id, state.key);
          heap.push({key: edge.id, node: String(edge.to), previous: edge, cost: total});
        }
      }
    }
    if (found === null) return {route: null, rejected};
    const edges = [];
    while (found !== '@origin') { edges.push(edgeById.get(found)); found = parents.get(found); }
    edges.reverse();
    return {route: routeSummary(edges, infos, network, options, recommended), rejected};
  }

  function plan(network, input) {
    const {options, destination} = validate(network, input), restrictions = new Map();
    for (const r of network.restrictions || []) {
      if (r.via_node === undefined || !r.restriction) continue;
      const key = `${r.from_way}|${r.via_node}`;
      if (!restrictions.has(key)) restrictions.set(key, []);
      restrictions.get(key).push(r);
    }
    const recommended = solve(network, options, destination, true, restrictions);
    const shortest = solve(network, options, destination, false, restrictions);
    return {status: recommended.route ? 'ok' : 'no_route', recommended: recommended.route, shortest: shortest.route, rejected: {recommended: recommended.rejected, shortest: shortest.rejected}, options, destination, origin: network.origin, assumptions: {speed_kmh: SPEED_KMH, turn_minutes: TURN_MINUTES, effective_width_by_highway_m: ASSUMED_WIDTHS, real_time_traffic: false, rejected_counts_scope: '도로망 전체 방향 구간 제외 수; turn_restriction은 탐색 중 제외 횟수'}, limitations: [...((network.meta || {}).limitations || []), '현장 유효폭은 rescue:verified_width 태그만 인정합니다.', `복합 via-way 등 미지원 회전제한 ${Number((network.meta || {}).unsupported_restriction_count || 0)}개 (스냅샷 기록 기준)`]};
  }
  return Object.freeze({plan});
});
