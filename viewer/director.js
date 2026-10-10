// ---------- animation (deterministic in t, so the director can render any frame) ----------
for (const a of animated) if (a.kind === "route") {
  a.cum = [0]; for (let i = 0; i < a.pts.length; i++) a.cum.push(a.cum[i] + a.pts[i].distanceTo(a.pts[(i + 1) % a.pts.length]));
}
function tick(t, wallLerp = 0.15) {
  for (const a of animated) {
    if (a.kind === "arm") { const j = a.obj.userData.joints, s = a.speed ?? 0.8, p = a.phase; j.yaw.rotation.y = j.pose[0] + Math.sin(t * s + p) * 0.9; j.sh.rotation.z = j.pose[1] + Math.sin(t * s * 1.3 + p) * 0.25; j.el.rotation.z = j.pose[2] + Math.sin(t * s * 1.1 + p + 1) * 0.3; }
    if (a.kind === "hover") { a.obj.position.set(a.base[0] + Math.sin(t * 0.7 + a.phase) * 0.6, a.base[1] + Math.sin(t * 1.7 + a.phase) * 0.12, a.base[2] + Math.cos(t * 0.5 + a.phase) * 0.6); a.obj.rotation.y = t * 0.4; }
    if (a.kind === "patrol") { const ang = t * 0.35 + a.phase; a.obj.position.set(a.c[0] + Math.cos(ang) * a.r, 0, a.c[1] + Math.sin(ang) * a.r); a.obj.rotation.y = -ang; }
    if (a.kind === "route") {
      const total = a.cum[a.cum.length - 1], d = (t * a.speed) % total; let i = 0; while (a.cum[i + 1] < d) i++;
      const p0 = a.pts[i], p1 = a.pts[(i + 1) % a.pts.length]; a.obj.position.lerpVectors(p0, p1, (d - a.cum[i]) / (a.cum[i + 1] - a.cum[i]));
      a.obj.rotation.y = Math.atan2(-(p1.z - p0.z), p1.x - p0.x);
    }
    if (a.kind === "sway") a.obj.rotation.z = Math.sin(t * 1.2) * 0.02;
  }
  for (const f of fadeWalls) {
    const toCam = camera.position.clone().sub(f.mid); toCam.y = 0;
    const facing = toCam.dot(f.n) > 0 && camera.position.y < 20;
    const target = facing ? 0.1 : 1; f.mesh.material.opacity += (target - f.mesh.material.opacity) * wallLerp;
    f.mesh.material.depthWrite = f.mesh.material.opacity > 0.9; f.mesh.castShadow = !facing;
  }
}

const TOUR = JSON.parse(document.getElementById("tour").textContent.trim().replace(/^\/\*TOUR\*\/$/, "null") || "null");
if (!TOUR) {
  const clock = new THREE.Clock();
  renderer.setAnimationLoop(() => {
    const t = clock.getElapsedTime();
    if (fly) {
      fly.t = Math.min(1, fly.t + 0.012); const k = fly.t * fly.t * (3 - 2 * fly.t);
      camera.position.lerpVectors(fly.p0, fly.p1, k); controls.target.lerpVectors(fly.t0, fly.t1, k); if (fly.t >= 1) fly = null;
    }
    tick(t); controls.update(); renderer.render(scene, camera);
  });
} else {
  director(TOUR);
}

// ---------- director: plays a tour.json timeline frame by frame ----------
function director(tour) {
  for (const id of ["views", "toggles", "legend", "title"]) document.getElementById(id).style.display = "none";
  controls.enabled = false;
  const css = document.createElement("style");
  css.textContent = `
    #ov { position:fixed; inset:0; pointer-events:none; font-family:Inter,-apple-system,Helvetica,Arial,sans-serif; color:#e6edf3; }
    .card { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; background:rgba(8,11,16,.82); backdrop-filter:blur(6px); }
    .cardin { width:min(1240px,86vw); }
    .kicker { font-size:22px; letter-spacing:.14em; text-transform:uppercase; color:#8b949e; margin-bottom:10px; }
    .big { font-size:96px; font-weight:800; letter-spacing:-.02em; margin:0; }
    .sub { font-size:34px; color:#c9d1d9; margin-top:14px; line-height:1.3; }
    .agentname { font-size:64px; font-weight:800; margin:0 0 6px; display:flex; align-items:center; gap:22px; }
    .dot { width:38px; height:38px; border-radius:50%; display:inline-block; flex:none; }
    .crit { list-style:none; padding:0; margin:28px 0 0; display:grid; gap:14px; }
    .crit li { font-size:29px; line-height:1.3; display:grid; grid-template-columns:44px 1fr auto; gap:14px; align-items:baseline; background:rgba(255,255,255,.05); border:1px solid rgba(255,255,255,.09); border-radius:12px; padding:14px 20px; }
    .crit .n { font-weight:800; }
    .crit .cite { font-size:20px; color:#8b949e; white-space:nowrap; }
    .hud { position:absolute; left:36px; top:32px; background:rgba(13,17,23,.85); border:1px solid #30363d; border-radius:14px; padding:14px 20px; font-size:26px; font-weight:650; display:flex; align-items:center; gap:14px; }
    .hud small { display:block; font-size:18px; color:#8b949e; font-weight:500; }
    .panel2 { position:absolute; left:36px; bottom:36px; width:min(1020px,62vw); background:rgba(13,17,23,.9); border:1px solid #30363d; border-radius:16px; padding:22px 26px; }
    .sev { display:inline-block; font-size:18px; font-weight:800; letter-spacing:.08em; padding:5px 12px; border-radius:6px; margin-right:12px; color:#fff; }
    .ftitle { font-size:34px; font-weight:750; margin:10px 0 8px; line-height:1.2; }
    .fdetail { font-size:25px; color:#c9d1d9; line-height:1.35; }
    .row { display:grid; grid-template-columns:150px 1fr; gap:8px 16px; margin-top:14px; font-size:23px; }
    .row b { color:#8b949e; font-weight:600; }
    .fix { color:#7ee787; }
    .cap { position:absolute; left:50%; bottom:92px; transform:translateX(-50%); background:rgba(13,17,23,.85); border:1px solid #30363d; border-radius:12px; padding:14px 22px; font-size:28px; white-space:nowrap; }
    table.sum { width:100%; border-collapse:collapse; margin-top:26px; font-size:24px; }
    table.sum th { text-align:left; color:#8b949e; font-weight:600; font-size:19px; text-transform:uppercase; letter-spacing:.06em; padding:10px 12px; border-bottom:1px solid #30363d; }
    table.sum td { padding:14px 12px; border-bottom:1px solid #21262d; vertical-align:top; }
    table.sum td.num { font-variant-numeric:tabular-nums; text-align:right; font-weight:700; }
    table.sum .top { font-size:19px; color:#c9d1d9; line-height:1.35; }
    .bar { height:12px; border-radius:6px; background:#21262d; overflow:hidden; margin-top:6px; } .bar i { display:block; height:100%; }
    .filterlabel { position:absolute; right:36px; top:32px; background:#6e40c9; color:#fff; font-size:22px; font-weight:700; padding:10px 16px; border-radius:10px; }
  `;
  document.head.append(css);
  document.body.insertAdjacentHTML("beforeend", `<div id="ov"></div>
  <svg width="0" height="0" style="position:absolute"><filter id="deutan" color-interpolation-filters="linearRGB">
    <feColorMatrix type="matrix" values="0.367322 0.860646 -0.227968 0 0  0.280085 0.672501 0.047413 0 0  -0.011820 0.042940 0.968881 0 0  0 0 0 1 0"/></filter></svg>`);
  const ov = document.getElementById("ov");
  const SEV = { blocking: "#d1242f", major: "#e8710a", minor: "#b58b00" };
  const esc = s => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;");

  // Avatars --------------------------------------------------------------------------------------
  function person(kind, color) {
    const g = new THREE.Group(), V = (x, y, z) => new THREE.Vector3(x, y, z);
    const skin = mat("skin", 0xc68e6a, { roughness: 0.7 }), cloth = mat("cloth" + color, new THREE.Color(color), { roughness: 0.6 });
    const pants = mat("pants", 0x2b3240), legs = [];
    const seated = kind === "wheelchair";
    if (seated) {
      g.userData.wheels = [];
      for (const sz of [-1, 1]) { const w = new THREE.Mesh(new THREE.TorusGeometry(0.3, 0.025, 10, 32), dark()); w.position.set(-0.05, 0.3, sz * 0.3); g.add(w); g.userData.wheels.push(w); }
      box(0.46, 0.05, 0.44, dark(), 0, 0.48, 0, g); box(0.05, 0.45, 0.44, dark(), -0.23, 0.5, 0, g);
      cyl(0.04, 0.04, 0.04, dark(), 0.25, 0.04, 0.17, g); cyl(0.04, 0.04, 0.04, dark(), 0.25, 0.04, -0.17, g);
      limb(V(0.0, 0.56, 0.1), V(0.38, 0.56, 0.1), 0.065, pants, g); limb(V(0.38, 0.56, 0.1), V(0.42, 0.12, 0.1), 0.055, pants, g);
      limb(V(0.0, 0.56, -0.1), V(0.38, 0.56, -0.1), 0.065, pants, g); limb(V(0.38, 0.56, -0.1), V(0.42, 0.12, -0.1), 0.055, pants, g);
      box(0.24, 0.5, 0.38, cloth, -0.08, 0.56, 0, g); sphere(0.11, skin, -0.06, 1.24, 0, g);
      limb(V(-0.06, 1.0, 0.22), V(0.05, 0.72, 0.28), 0.045, cloth, g); limb(V(-0.06, 1.0, -0.22), V(0.05, 0.72, -0.28), 0.045, cloth, g);
    } else {
      for (const sz of [-1, 1]) { const l = new THREE.Group(); l.position.set(0, 0.92, sz * 0.1); g.add(l); limb(V(0, 0, 0), V(0, -0.88, 0), 0.07, pants, l); box(0.24, 0.07, 0.11, dark(), 0.05, -0.92, 0, l); legs.push(l); }
      box(0.26, 0.6, 0.4, cloth, 0, 0.9, 0, g); sphere(0.115, skin, 0, 1.63, 0, g);
      const arms = [];
      for (const sz of [-1, 1]) { const a = new THREE.Group(); a.position.set(0, 1.44, sz * 0.25); g.add(a); limb(V(0, 0, 0), V(0, -0.6, 0), 0.05, cloth, a); arms.push(a); }
      g.userData.arms = arms;
      if (kind === "cane") { box(0.04, 0.05, 0.22, black(), 0.1, 1.62, 0, g); const c = cyl(0.012, 0.012, 1.25, white(), 0, 0, 0, g); c.position.set(0.45, 0.55, 0.28); c.rotation.z = -0.55; box(0.06, 0.12, 0.012, red(), 0.62, 0.0, 0.28, g); }
      if (kind === "headphones") { const h = new THREE.Mesh(new THREE.TorusGeometry(0.13, 0.02, 8, 24, Math.PI), dark()); h.position.set(0, 1.65, 0); h.rotation.y = Math.PI / 2; g.add(h); sphere(0.05, cloth, 0, 1.62, 0.12, g); sphere(0.05, cloth, 0, 1.62, -0.12, g); }
      if (kind === "hivis") { box(0.28, 0.42, 0.42, mat("vest", 0xffd400, { emissive: 0x332b00 }), 0, 1.0, 0, g); box(0.29, 0.04, 0.43, mat("refl", 0xe0e0e0, { metalness: 0.8, roughness: 0.2 }), 0, 1.1, 0, g); sphere(0.13, mat("helmet", 0xffffff), 0, 1.7, 0, g); }
    }
    g.userData.legs = legs; g.userData.seated = seated;
    g.traverse(o => { if (o.isMesh) o.castShadow = true; });
    return g;
  }
  const avatars = {};
  function avatarFor(seg) {
    if (!avatars[seg.agent]) { avatars[seg.agent] = person(seg.avatar, seg.color); scene.add(avatars[seg.agent]); }
    return avatars[seg.agent];
  }
  function pose(av, s) {
    const sw = Math.sin(s * 5.2) * 0.5;
    av.userData.legs?.forEach((l, i) => (l.rotation.z = i ? sw : -sw));
    av.userData.arms?.forEach((a, i) => (a.rotation.z = (i ? -sw : sw) * 0.6));
    av.userData.wheels?.forEach(w => (w.rotation.z = -s / 0.3));
  }

  // Path helpers ---------------------------------------------------------------------------------
  function along(path, d) {
    let acc = 0;
    for (let i = 0; i < path.length - 1; i++) {
      const a = path[i], b = path[i + 1], L = Math.hypot(b[0] - a[0], b[1] - a[1]);
      if (acc + L >= d || i === path.length - 2) { const u = L ? Math.min(1, (d - acc) / L) : 0; return [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, Math.atan2(b[1] - a[1], b[0] - a[0])]; }
      acc += L;
    }
    return [...path[0], 0];
  }
  const plen = path => path.reduce((s, p, i) => (i ? s + Math.hypot(p[0] - path[i - 1][0], p[1] - path[i - 1][1]) : 0), 0);
  for (const s of tour.segments) if (s.type === "walk") s.len = plen(s.path);

  // Finding markers ------------------------------------------------------------------------------
  const fx = new THREE.Group(); scene.add(fx);
  const beamMat = new THREE.MeshBasicMaterial({ color: 0xff3b30, transparent: true, opacity: 0.35, depthWrite: false, blending: THREE.AdditiveBlending });
  let highlighted = [];
  function clearFx() {
    fx.traverse(o => { o.geometry?.dispose?.(); });
    fx.clear();
    for (const [o, m] of highlighted) o.material = m;
    highlighted = [];
    renderer.domElement.style.filter = "";
  }
  function highlight(id, color) {
    const g = groups[id]; if (!g) return;
    g.traverse(o => {
      if (!o.isMesh || !o.material?.emissive || o.userData.zoneFloor) return;
      const m = o.material.clone(); m.emissive.set(color); m.emissiveIntensity = 0.55;
      highlighted.push([o, o.material]); o.material = m;
    });
  }
  function marker(loc, t) {
    const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 3.2, 12, 1, true), beamMat); beam.position.copy(P(loc[0], loc[1], 1.6)); fx.add(beam);
    for (let k = 0; k < 3; k++) {
      const ph = ((t * 0.9 + k / 3) % 1), r = 0.25 + ph * 0.9;
      const ring = new THREE.Mesh(new THREE.RingGeometry(r, r + 0.05, 48), new THREE.MeshBasicMaterial({ color: 0xff3b30, transparent: true, opacity: 0.9 * (1 - ph), side: THREE.DoubleSide, depthWrite: false }));
      ring.rotation.x = -Math.PI / 2; ring.position.copy(P(loc[0], loc[1], 0.02)); fx.add(ring);
    }
    const pin = new THREE.Mesh(new THREE.SphereGeometry(0.12, 20, 14), new THREE.MeshBasicMaterial({ color: 0xff3b30 })); pin.position.copy(P(loc[0], loc[1], 3.2 + Math.sin(t * 3) * 0.06)); fx.add(pin);
  }
  function reachViz(r) {
    const disc = new THREE.Mesh(new THREE.CircleGeometry(r.r, 64), new THREE.MeshBasicMaterial({ color: 0xff3b30, transparent: true, opacity: 0.28, depthWrite: false }));
    disc.rotation.x = -Math.PI / 2; disc.position.copy(P(r.center[0], r.center[1], 0.03)); fx.add(disc);
    const edge = new THREE.Mesh(new THREE.RingGeometry(r.r - 0.03, r.r, 96), new THREE.MeshBasicMaterial({ color: 0xff3b30, side: THREE.DoubleSide }));
    edge.rotation.x = -Math.PI / 2; edge.position.copy(P(r.center[0], r.center[1], 0.035)); fx.add(edge);
    const zone = new THREE.Line(new THREE.BufferGeometry().setFromPoints(r.zone.map(([x, y]) => P(x, y, 0.05))), new THREE.LineBasicMaterial({ color: 0x00e5ff }));
    fx.add(zone);
  }
  function noiseViz(n, t) {
    for (let k = 0; k < 5; k++) {
      const ph = ((t * 0.6 + k / 5) % 1), r = 0.4 + ph * 5.5;
      const ring = new THREE.Mesh(new THREE.RingGeometry(r, r + 0.06, 64), new THREE.MeshBasicMaterial({ color: 0xffa657, transparent: true, opacity: 0.7 * (1 - ph), side: THREE.DoubleSide, depthWrite: false }));
      ring.rotation.x = -Math.PI / 2; ring.position.copy(P(n.source[0], n.source[1], 0.04)); fx.add(ring);
    }
  }

  // Cameras --------------------------------------------------------------------------------------
  const ease = u => u * u * (3 - 2 * u);
  const clampX = x => Math.min(W - 0.35, Math.max(0.35, x)), clampY = y => Math.min(D - 0.35, Math.max(0.35, y));
  function walkCam(x, y, h, seated) {
    const back = 2.7, up = 2.9;
    return [P(clampX(x - Math.cos(h) * back), clampY(y - Math.sin(h) * back), up), P(x + Math.cos(h) * 1.0, y + Math.sin(h) * 1.0, seated ? 0.7 : 1.0)];
  }
  function stopCam(seg, u) {
    const f = seg.finding, L = f.location, A = seg.at;
    let dx = A[0] - L[0], dy = A[1] - L[1], n = Math.hypot(dx, dy);
    if (n < 0.3) { dx = -1; dy = -0.6; n = Math.hypot(dx, dy); }
    const ang = Math.atan2(dy, dx) + (u - 0.5) * 0.5;
    const dist = seg.reach ? 4.6 : seg.noise ? 6.5 : seg.sign ? 2.6 : seg.filter ? 9 : 3.8;
    const hgt = seg.reach ? 4.0 : seg.noise ? 6.0 : seg.sign ? seg.sign.height + 0.2 : seg.filter ? 10 : 2.4;
    const ly = seg.sign ? seg.sign.height : 0.9;
    return [P(clampX(L[0] + Math.cos(ang) * dist), clampY(L[1] + Math.sin(ang) * dist), hgt), P(L[0], L[1], ly)];
  }
  let lastCam = [P(W / 2 - 9, -6, 17), P(W / 2, D / 2, 0)];
  function setCam([p, t]) { camera.position.copy(p); controls.target.copy(t); camera.lookAt(t); }
  function blend(a, b, k) { return [a[0].clone().lerp(b[0], k), a[1].clone().lerp(b[1], k)]; }
  function orbitCam(T, high) { const ang = -1.9 + T * 0.03, r = 15; return [P(W / 2 + Math.cos(ang) * r, D / 2 + Math.sin(ang) * r, high ? 13 : 10), P(W / 2, D / 2, 0)]; }

  // Overlay templates ----------------------------------------------------------------------------
  function cardHTML(s) {
    if (s.kind === "title" || s.kind === "end")
      return `<div class="card"><div class="cardin"><div class="kicker">Future of Work Hackathon · Track 1: Accessible Workplace Twin</div><h1 class="big">${esc(s.title)}</h1><div class="sub">${esc(s.subtitle)}</div></div></div>`;
    if (s.kind === "agent")
      return `<div class="card"><div class="cardin"><div class="kicker">Agent · ${s.stats.checks} checks on this design</div>
        <h2 class="agentname"><span class="dot" style="background:${s.color}"></span>${esc(s.name)}</h2><div class="sub" style="font-size:28px">${esc(s.summary)}</div>
        <div class="kicker" style="margin-top:30px">What this agent checks</div>
        <ul class="crit">${s.criteria.map((c, i) => `<li><span class="n" style="color:${s.color}">${i + 1}</span><span>${esc(c.text)}</span><span class="cite">${esc(c.cite)}</span></li>`).join("")}</ul></div></div>`;
    if (s.kind === "summary")
      return `<div class="card"><div class="cardin" style="width:min(1500px,92vw)"><div class="kicker">Summary · overall score ${s.overall.toFixed(0)}%</div><h2 class="agentname" style="font-size:52px">${esc(s.title)}</h2>
        <table class="sum"><tr><th>Agent</th><th style="text-align:right">Checks</th><th style="text-align:right">Failed</th><th style="text-align:right">Blocking</th><th style="text-align:right">Major</th><th style="text-align:right">Minor</th><th>Score</th><th>Top findings</th></tr>
        ${s.rows.map(r => `<tr><td style="font-weight:750;white-space:nowrap"><span class="dot" style="width:16px;height:16px;background:${r.color};margin-right:10px"></span>${esc(r.agent)}</td>
          <td class="num">${r.checks}</td><td class="num">${r.failed}</td><td class="num" style="color:${r.blocking ? "#ff7b72" : "#8b949e"}">${r.blocking}</td><td class="num">${r.major}</td><td class="num">${r.minor}</td>
          <td style="width:150px"><b>${r.score.toFixed(0)}%</b><div class="bar"><i style="width:${r.score}%;background:${r.color}"></i></div></td>
          <td class="top">${r.top.map(esc).join("<br>")}</td></tr>`).join("")}</table></div></div>`;
    return "";
  }
  const names = {}; for (const s of tour.segments) if (s.kind === "agent") names[s.agent] = s.name;
  const agentName = id => names[id] || id;
  function stopHTML(s) {
    const f = s.finding;
    return `<div class="hud"><span class="dot" style="width:22px;height:22px;background:${s.color}"></span><div>${esc(agentName(s.agent))}<small>Finding ${s.index} of ${s.of}</small></div></div>
      ${s.filter ? `<div class="filterlabel">Simulated deuteranopia (red-green color blindness)</div>` : ""}
      <div class="panel2"><span class="sev" style="background:${SEV[f.severity]}">${f.severity.toUpperCase()}</span><span style="color:#8b949e;font-size:20px">${esc(f.citation)}</span>
        <div class="ftitle">${esc(f.title)}</div><div class="fdetail">${esc(f.detail)}</div>
        <div class="row"><b>Required</b><span>${esc(f.required)}</span>${f.fix ? `<b>Fix</b><span class="fix">${esc(f.fix)}</span>` : ""}</div></div>`;
  }
  let lastHTML = "";
  function overlay(html) { if (html !== lastHTML) { ov.innerHTML = html; lastHTML = html; } }

  // Photoreal worlds (World Labs Marble splats), one per finding ---------------------------------
  const worldStops = tour.segments.filter(s => s.world);
  const procedural = scene.children.filter(o => o !== fx);  // the procedural twin (not the finding markers)
  const splatGroups = {};
  let pointsObj = null, lastWorld = null;
  window.splatsReady = (async () => {
    if (!worldStops.length) return;
    const { SplatMesh, SparkRenderer } = await import("@sparkjsdev/spark");
    scene.add(new SparkRenderer({ renderer }));
    await Promise.all(worldStops.map(async s => {
      const w = s.world, g = new THREE.Group();
      const eye = P(...s.hero.eye), tgt = P(...s.hero.target);
      g.position.set(eye.x, w.ground, eye.z);  // Marble camera height above its ground plane = w.ground (m)
      g.rotation.y = Math.atan2(-(tgt.x - eye.x), -(tgt.z - eye.z));  // Marble camera looks down -Z
      const m = new SplatMesh({ url: w.url });
      m.quaternion.set(1, 0, 0, 0);  // OpenCV -> three.js axes
      m.scale.setScalar(w.scale);
      g.add(m); g.visible = false; scene.add(g);
      await m.initialized;
      splatGroups[s.hero.index] = g;
    }));
  })();
  // Hide / restore the procedural twin without disturbing things that were already hidden (e.g. the Design B set).
  function twinVisible(on) {
    for (const o of procedural) {
      if (o.isLight) continue;
      if (!on && o.visible) { o.visible = false; o.userData.hiddenByDirector = true; }
      if (on && o.userData.hiddenByDirector) { o.visible = true; o.userData.hiddenByDirector = false; }
    }
  }
  function showWorld(seg, mode) {
    const g = seg && seg.world ? splatGroups[seg.hero.index] : null;
    for (const k in splatGroups) splatGroups[k].visible = splatGroups[k] === g;
    if (pointsObj) pointsObj.visible = mode === "points";
    twinVisible(!g && mode !== "points");
    scene.background = g || mode === "points" ? new THREE.Color(0x05070a) : new THREE.Color(0x0d1117);
    return g;
  }
  function outlineBox(id) {
    const g = groups[id]; if (!g) return;
    const e = g.userData.el, [w, d] = e.size, h = Math.max(0.3, e.height);
    const box3 = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(w + 0.08, h + 0.04, d + 0.08)),
      new THREE.LineBasicMaterial({ color: 0xff2d2d, linewidth: 2, depthTest: false }));
    box3.position.copy(g.position).setY(h / 2); box3.rotation.copy(g.rotation); box3.renderOrder = 20; fx.add(box3);
  }


  // Point cloud of the real scan (story chapters "scan" and "clean") -----------------------------
  const scanSeg = tour.segments.find(s => s.type === "scan" || s.type === "clean");
  const pointsReady = (async () => {
    if (!scanSeg) return;
    const buf = await (await fetch(scanSeg.points)).arrayBuffer();
    const n = buf.byteLength / 16, dv = new DataView(buf);
    const pos = new Float32Array(n * 3), col = new Float32Array(n * 3), flg = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const o = i * 16, x = dv.getFloat32(o, true), y = dv.getFloat32(o + 4, true), z = dv.getFloat32(o + 8, true);
      pos[i * 3] = x; pos[i * 3 + 1] = z; pos[i * 3 + 2] = -y;
      col[i * 3] = dv.getUint8(o + 12) / 255; col[i * 3 + 1] = dv.getUint8(o + 13) / 255; col[i * 3 + 2] = dv.getUint8(o + 14) / 255;
      flg[i] = dv.getUint8(o + 15);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
    geo.setAttribute("flag", new THREE.BufferAttribute(flg, 1));
    const m = new THREE.ShaderMaterial({
      uniforms: { uClean: { value: 0 }, uRefill: { value: 0 }, uSize: { value: 0.075 }, uScale: { value: innerHeight / 2 } },
      vertexShader: `attribute vec3 color; attribute float flag; uniform float uClean, uRefill, uSize, uScale; varying vec3 vC; varying float vA;
        void main(){ vec4 mv = modelViewMatrix * vec4(position, 1.0); gl_Position = projectionMatrix * mv;
          vC = color; vA = 1.0; float s = uSize;
          if (flag > 0.5 && flag < 1.5) { float r = smoothstep(0.0, 0.35, uClean); vC = mix(color, vec3(1.0, 0.18, 0.15), r);
            float gone = smoothstep(0.45, 1.0, uClean); vA = 1.0 - gone; s *= 1.0 - gone; }
          if (flag > 1.5) { vA = uRefill; s *= uRefill; }
          gl_PointSize = max(1.0, s * uScale / -mv.z); }`,
      fragmentShader: `varying vec3 vC; varying float vA; void main(){ vec2 c = gl_PointCoord - 0.5; if (dot(c, c) > 0.25 || vA < 0.02) discard; gl_FragColor = vec4(vC, vA); }`,
      transparent: true, depthWrite: true,
    });
    pointsObj = new THREE.Points(geo, m); pointsObj.visible = false; pointsObj.frustumCulled = false; scene.add(pointsObj);
  })();
  const prevReady = window.splatsReady;
  window.splatsReady = Promise.all([prevReady, pointsReady]);

  // Build-up (stations drop into the empty room zone by zone) and A -> B morph ---------------------
  const zoneOrder = (spec.zones || []).map(z => z.id);
  const elOrder = Object.values(groups).sort((a, b) => zoneOrder.indexOf(a.userData.el.zone) - zoneOrder.indexOf(b.userData.el.zone));
  const homeA = Object.fromEntries(Object.entries(groups).map(([id, g]) => [id, { p: g.position.clone(), r: g.rotation.y }]));
  function resetA() {
    for (const [id, g] of Object.entries(groups)) { g.position.copy(homeA[id].p); g.rotation.y = homeA[id].r; g.scale.setScalar(1); g.visible = true; }
    for (const g of Object.values(groupsB)) g.visible = false;
    for (const s of signs) if (s.userData.designB) s.visible = false;
  }
  function buildUp(u) {
    const n = elOrder.length;
    elOrder.forEach((g, i) => {
      const t0 = 0.05 + 0.75 * i / n, k = Math.min(1, Math.max(0, (u - t0) / 0.12));
      g.visible = k > 0; g.scale.set(1, Math.max(0.001, ease(k)), 1); g.position.y = (1 - ease(k)) * 1.2;
    });
  }
  function morph(u) {
    const k = ease(Math.min(1, u / 0.6));
    for (const [id, g] of Object.entries(groups)) {
      const b = groupsB[id];
      if (b) { g.position.lerpVectors(homeA[id].p, b.position, k); g.rotation.y = homeA[id].r + (b.rotation.y - homeA[id].r) * k; g.visible = u < 0.62; }
      else { g.scale.setScalar(Math.max(0.001, 1 - ease(Math.min(1, u / 0.4)))); g.visible = u < 0.4; }  // removed in B
    }
    for (const [id, b] of Object.entries(groupsB)) {
      if (groups[id]) b.visible = u >= 0.62;
      else { const kk = Math.min(1, Math.max(0, (u - 0.62) / 0.15)); b.visible = kk > 0; b.scale.set(1, Math.max(0.001, ease(kk)), 1); }  // new in B
    }
  }
  function storyCam(T, high = 12, r = 14) { const ang = -1.7 + T * 0.035; return [P(W / 2 + Math.cos(ang) * r, D / 2 + Math.sin(ang) * r, high), P(W / 2, D / 2, 0.4)]; }

  // Story cards ------------------------------------------------------------------------------------
  function storyCard(s, u) {
    const reveal = (i, n) => `style="opacity:${Math.min(1, Math.max(0, (u * (n + 2) - i) ))};transform:translateY(${Math.max(0, 10 - (u * (n + 2) - i) * 10)}px)"`;
    if (s.kind === "problem" || s.kind === "solution" || s.kind === "demo")
      return `<div class="card"><div class="cardin"><div class="kicker">${esc(s.kicker || "")}</div><h1 class="big" style="font-size:72px">${esc(s.title)}</h1>
        ${(s.points || []).map((p, i) => `<div class="sub" ${reveal(i + 1, s.points.length)}>${esc(p)}</div>`).join("")}${s.svg || ""}</div></div>`;
    if (s.kind === "research")
      return `<div class="card"><div class="cardin" style="width:min(1500px,92vw)"><div class="kicker">Research agent · ${s.sources} cited sources</div><h2 class="agentname" style="font-size:52px">${esc(s.title)}</h2>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:22px">${s.zones.map((z, i) => `<div ${reveal(i, s.zones.length)} class="zcard"><b>${esc(z.label)}</b><span>${z.items} items · ${z.reqs} requirements</span><em>${esc(z.example)}</em></div>`).join("")}</div></div></div>`;
    if (s.kind === "metrics")
      return `<div class="card"><div class="cardin" style="width:min(1500px,92vw)"><div class="kicker">Results</div><h2 class="agentname" style="font-size:56px">${esc(s.title)}</h2>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:24px 0">${s.tiles.map((t, i) => `<div ${reveal(i, 4)} class="tile"><span>${esc(t.label)}</span><b><s>${esc(t.a)}</s> → ${esc(t.b)}</b></div>`).join("")}</div>
        <table class="sum"><tr><th>Agent</th><th style="text-align:right">A failed</th><th style="text-align:right">A blocking</th><th>A score</th><th style="text-align:right">B failed</th><th style="text-align:right">B blocking</th><th>B score</th></tr>
        ${s.rows.map(r => `<tr><td style="font-weight:750"><span class="dot" style="width:16px;height:16px;background:${r.color};margin-right:10px"></span>${esc(r.agent)}</td><td class="num">${r.a_failed}</td><td class="num">${r.a_blocking}</td>
          <td style="width:170px"><b>${r.a_score.toFixed(0)}%</b><div class="bar"><i style="width:${r.a_score}%;background:${r.color};opacity:.5"></i></div></td><td class="num">${r.b_failed}</td><td class="num">${r.b_blocking}</td>
          <td style="width:170px"><b>${r.b_score.toFixed(0)}%</b><div class="bar"><i style="width:${r.b_score}%;background:${r.color}"></i></div></td></tr>`).join("")}</table></div></div>`;
    return cardHTML(s);
  }
  const chapters = tour.segments.filter(s => s.chapter);
  function chrome(T, seg) {
    const ch = [...tour.segments].reverse().find(s => s.chapter && s.t0 <= T + 1e-6);
    const idx = ch ? chapters.indexOf(ch) + 1 : 0;
    return (ch ? `<div class="chapter">${idx}/${chapters.length} · ${esc(ch.chapter)}</div>` : "")
      + `<div class="progress"><i style="width:${(100 * T / tour.duration).toFixed(2)}%"></i></div>`
      + (seg.caption && seg.type !== "orbit" ? `<div class="cap">${esc(seg.caption)}</div>` : "");
  }
  css.textContent += `
    .chapter { position:absolute; right:36px; bottom:36px; font-size:20px; color:#c9d1d9; background:rgba(13,17,23,.75); border:1px solid #30363d; border-radius:10px; padding:8px 14px; }
    .progress { position:absolute; left:0; right:0; bottom:0; height:6px; background:rgba(255,255,255,.08); } .progress i { display:block; height:100%; background:#58a6ff; }
    .zcard { background:rgba(255,255,255,.05); border:1px solid rgba(255,255,255,.1); border-radius:12px; padding:14px 16px; display:flex; flex-direction:column; gap:4px; font-size:24px; }
    .zcard span { color:#8b949e; font-size:18px; } .zcard em { color:#7ee787; font-size:17px; font-style:normal; }
    .tile { background:rgba(255,255,255,.05); border:1px solid rgba(255,255,255,.1); border-radius:14px; padding:18px; } .tile span { color:#8b949e; font-size:20px; display:block; }
    .tile b { font-size:44px; } .tile s { color:#ff7b72; text-decoration-thickness:3px; font-weight:600; }
    .fade { position:absolute; inset:0; background:#000; }
    .changes { position:absolute; right:36px; top:32px; width:560px; background:rgba(13,17,23,.9); border:1px solid #30363d; border-radius:16px; padding:18px 22px; font-size:22px; }
    .changes li { margin:8px 0; } .changes li b { color:#7ee787; }
  `;

  // Frame ----------------------------------------------------------------------------------------
  window.TOUR_DURATION = tour.duration;
  window.renderAt = function (T) {
    let i = tour.segments.findIndex(s => T < s.t0 + s.dur); if (i < 0) i = tour.segments.length - 1;
    const seg = tour.segments[i], u = Math.min(1, (T - seg.t0) / seg.dur), tl = T - seg.t0;
    clearFx();
    for (const a of Object.values(avatars)) a.visible = false;
    let cam;
    const next = tour.segments[i + 1];
    const worldSeg = seg.world ? seg : (seg.type === "walk" && next?.world ? next : null);
    const pointsMode = seg.type === "scan" || seg.type === "clean" || (seg.type === "card" && seg.backdrop === "points");
    const wg = showWorld(worldSeg, pointsMode ? "points" : null);
    if (wg !== lastWorld) { window.__settle = 20; lastWorld = wg; }  // Spark sorts splats asynchronously
    const fadeIn = seg.fade ? Math.max(0, 1 - tl / 0.6) : 0, fadeOut = seg.fadeOut ? Math.max(0, 1 - (seg.dur - tl) / 0.6) : 0;
    const fadeHTML = (fadeIn || fadeOut) ? `<div class="fade" style="opacity:${Math.max(fadeIn, fadeOut).toFixed(3)}"></div>` : "";
    if (["scan", "clean", "build", "morph"].includes(seg.type) || (seg.type === "card" && seg.backdrop)) {
      if (pointsMode) twinVisible(false);
      else if (seg.type === "build" || (seg.type === "card" && seg.backdrop === "build")) { resetA(); buildUp(seg.type === "build" ? u : 0); }
      else if (seg.type === "morph") { resetA(); morph(u); }
      else if (seg.backdrop === "designB") { resetA(); morph(1); }
      else resetA();
      if (pointsObj) {
        pointsObj.material.uniforms.uClean.value = seg.type === "clean" ? Math.min(1, u / 0.7) : (seg.after === "clean" ? 1 : 0);
        pointsObj.material.uniforms.uRefill.value = seg.type === "clean" ? Math.max(0, (u - 0.6) / 0.4) : (seg.after === "clean" ? 1 : 0);
        pointsObj.material.uniforms.uScale.value = innerHeight / 2;
      }
      cam = storyCam(T, seg.type === "morph" ? 13 : 12, seg.type === "scan" || seg.type === "clean" ? 12 : 14.5);
      setCam(cam); lastCam = cam;
      let html = seg.type === "card" ? storyCard(seg, u) : "";
      if (seg.type === "morph" && seg.changes) html += `<div class="changes"><div class="kicker" style="font-size:16px">Remediation agent</div><ul style="padding-left:20px;margin:6px 0">${seg.changes.map((c, j) => `<li style="opacity:${u * (seg.changes.length + 1) > j ? 1 : 0.15}">${c}</li>`).join("")}</ul></div>`;
      overlay(html + chrome(T, seg) + fadeHTML);
      tick(T, 0.3); renderer.render(scene, camera);
      return seg.type;
    }
    if (wg) {
      const h = worldSeg.hero, eye = P(...h.eye), tgt = P(...h.target), f = worldSeg.finding;
      const dir = tgt.clone().sub(eye).setY(0).normalize();
      // Photoreal shots stay on the Marble capture camera (the splat is only valid near it), with a slow push-in.
      if (seg.type === "walk") {
        overlay(`<div class="hud"><span class="dot" style="width:22px;height:22px;background:${seg.color}"></span><div>${esc(agentName(seg.agent))}<small>${esc(seg.label.split(": ")[1] || "")}</small></div></div><div class="filterlabel" style="background:#1f6feb">Photoreal world · World Labs Marble</div>` + chrome(T, seg) + fadeHTML);
        cam = [eye.clone().addScaledVector(dir, 0.25 * ease(u)), tgt];
      } else {
        if (f.element_id) outlineBox(f.element_id);
        if (seg.noise) { outlineBox(seg.noise.source_id); noiseViz(seg.noise, T); }
        if (seg.reach) reachViz(seg.reach);
        marker(f.location, T);
        cam = [eye.clone().addScaledVector(dir, 0.25 + 0.45 * ease(u)), tgt];
        overlay(stopHTML(seg) + `<div class="filterlabel" style="background:#1f6feb;top:${seg.filter ? 86 : 32}px">Photoreal world · World Labs Marble</div>` + chrome(T, seg) + fadeHTML);
        if (seg.filter) renderer.domElement.style.filter = "url(#deutan)";
      }
      setCam(cam); lastCam = cam;
      renderer.render(scene, camera);
      return seg.type;
    }
    if (seg.type === "card" || seg.type === "orbit") {
      cam = orbitCam(T, seg.type === "card");
      overlay((seg.type === "card" ? storyCard(seg, u) : `<div class="cap">${esc(seg.caption)}</div>`) + chrome(T, seg) + fadeHTML);
      lastCam = cam;
    } else if (seg.type === "walk") {
      const av = avatarFor(seg); av.visible = true;
      const d = seg.len * ease(u), [x, y, h] = along(seg.path, d), [, , h2] = along(seg.path, Math.min(seg.len, d + 1.0));
      const hh = Math.atan2(Math.sin(h) + Math.sin(h2), Math.cos(h) + Math.cos(h2));
      av.position.copy(P(x, y, 0)); av.rotation.y = hh; pose(av, d);
      cam = walkCam(x, y, hh, av.userData.seated);
      if (tl < 0.9) cam = blend(seg.from || lastCam, cam, ease(tl / 0.9)); else seg.from = seg.from || lastCam;
      if (tl < 0.9 && !seg.from) seg.from = lastCam;
      overlay(`<div class="hud"><span class="dot" style="width:22px;height:22px;background:${seg.color}"></span><div>${esc(agentName(seg.agent))}<small>${esc(seg.label.split(": ")[1] || "")}</small></div></div>`
        + (seg.agent === "low_vision" ? `<div class="filterlabel">Simulated low vision</div>` : ""));
      if (seg.agent === "low_vision") renderer.domElement.style.filter = "blur(1.6px) contrast(.75)";
    } else if (seg.type === "stop") {
      const av = avatarFor(seg); av.visible = true; av.position.copy(P(seg.at[0], seg.at[1], 0));
      const f = seg.finding; av.rotation.y = Math.atan2(f.location[1] - seg.at[1], f.location[0] - seg.at[0]); pose(av, 0);
      if (f.element_id) highlight(f.element_id, 0xff2d2d);
      if (seg.noise) { highlight(seg.noise.source_id, 0xff8c00); noiseViz(seg.noise, T); }
      if (seg.reach) reachViz(seg.reach);
      marker(f.location, T);
      if (seg.filter) renderer.domElement.style.filter = "url(#deutan)";
      cam = stopCam(seg, u);
      if (!seg.from) seg.from = lastCam;
      if (tl < 1.0) cam = blend(seg.from, cam, ease(tl / 1.0));
      overlay(stopHTML(seg) + chrome(T, seg) + fadeHTML);
      lastCam = cam;
    }
    if (seg.type === "walk") lastCam = cam;
    setCam(cam);
    tick(T, 0.3);
    renderer.render(scene, camera);
    return seg.type;
  };
  // Live preview when opened in a browser: play in real time.
  if (!new URLSearchParams(location.search).has("record")) {
    const t0 = performance.now();
    renderer.setAnimationLoop(() => window.renderAt(((performance.now() - t0) / 1000) % tour.duration));
  }
}
