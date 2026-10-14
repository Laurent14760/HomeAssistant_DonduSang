/*
 * efs-collectes-card – carte Lovelace de l'intégration efs_dondesang.
 * Reprend les trois visuels : synthèse de la prochaine collecte, agenda, carte et remplissage.
 *
 *   type: custom:efs-collectes-card
 *   vue: synthese | agenda | carte | complet   (défaut : complet)
 *   entity: sensor.efs_prochaine_collecte       (défaut)
 *   agenda_entity: sensor.efs_collectes_a_venir (défaut)
 *   max: 6                                      (lignes d'agenda)
 *   couleur: "#B42318"                          (accent)
 */
(() => {
  const VERSION = "1.1.0";
  const TZ_FALLBACK = "Europe/Paris";
  const DON = { sang: "Sang total", plasma: "Plasma", plaquettes: "Plaquettes" };
  const ST = { OUVERT: "Planning ouvert", NON: "Planning non ouvert", COMPLET: "Complet" };

  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const safeUrl = (u) => {
    if (typeof u !== "string" || !u.trim()) return null;
    const v = u.trim();
    if (/^https?:\/\//i.test(v)) return v;
    if (/^[a-z][a-z0-9+.-]*:/i.test(v)) return null;
    return "https://" + v.replace(/^\/\//, "");
  };
  const num = (v) => (v === null || v === undefined || v === "" || v === "unknown" || v === "unavailable" || isNaN(Number(v)) ? null : Number(v));
  const nf = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });
  const km = (v) => (v === null || v === undefined ? "" : `${nf.format(v)} km`);
  const pct = (v) => `${Math.round(v)} %`;
  const titre = (s) => String(s || "").toLowerCase()
    .replace(/(^|[\s\-'’(])([a-zà-ÿ])/g, (m, a, b) => a + b.toUpperCase());

  function statutDe(restantes) {
    if (restantes === null) return ST.NON;
    return restantes <= 0 ? ST.COMPLET : ST.OUVERT;
  }
  function chip(statut) {
    if (statut === ST.COMPLET) return `<span class="chip full">Complet</span>`;
    if (statut === ST.NON) return `<span class="chip neutral">Planning non ouvert</span>`;
    return `<span class="chip ok">Planning ouvert</span>`;
  }

  const ICON_DROP = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 2.7c3.6 4.6 6 8 6 11.3a6 6 0 0 1-12 0c0-3.3 2.4-6.7 6-11.3z"/></svg>`;
  const ICON_PIN = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 21s-7-6.1-7-11.5A7 7 0 0 1 19 9.5C19 14.9 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/></svg>`;

  const STYLE = `
    :host{--efs-accent:#B42318;--efs-accent-text:var(--efs-accent);--efs-accent-soft:rgba(180,35,24,.12);--efs-ok:#0B6E4F;--efs-ok-soft:rgba(11,110,79,.13);
      --efs-text:var(--primary-text-color,#1C1F24);--efs-muted:var(--secondary-text-color,#5A6170);
      --efs-line:var(--divider-color,rgba(0,0,0,.12));--efs-soft:var(--secondary-background-color,#F6F7F9);
      --efs-chip:rgba(127,127,127,.16);--efs-map:rgba(127,140,133,.16);--efs-grid:rgba(127,140,133,.28)}
    ha-card.dark{--efs-accent-text:#FF8A78;--efs-ok:#5FD3A6;--efs-ok-soft:rgba(95,211,166,.16);--efs-accent-soft:rgba(240,100,79,.18)}
    ha-card{padding:16px;color:var(--efs-text);display:flex;flex-direction:column;gap:20px}
    .bloc{display:flex;flex-direction:column;gap:16px}
    .bloc+.bloc{border-top:1px solid var(--efs-line);padding-top:20px}
    .row{display:flex;align-items:center;justify-content:space-between;gap:12px}
    .left{justify-content:flex-start}
    .muted{color:var(--efs-muted)}
    .small{font-size:13px}.xs{font-size:12px}
    .h{font-size:17px;font-weight:600}
    .icon{width:36px;height:36px;border-radius:10px;background:var(--efs-accent-soft);color:var(--efs-accent-text);display:flex;align-items:center;justify-content:center;flex:none}
    .chip{font-size:12px;font-weight:600;padding:3px 10px;border-radius:999px;white-space:nowrap;display:inline-block}
    .chip.neutral{background:var(--efs-chip);color:var(--efs-muted)}
    .chip.ok{background:var(--efs-ok-soft);color:var(--efs-ok)}
    .chip.full{background:var(--efs-accent-soft);color:var(--efs-accent-text)}
    .kicker{font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--efs-muted)}
    .date{font-size:28px;font-weight:700;line-height:1.15;margin:2px 0}
    .place{display:flex;gap:12px;padding:12px 14px;background:var(--efs-soft);border-radius:12px}
    .place svg{flex:none;margin-top:2px;color:var(--efs-muted)}
    .big{font-size:38px;font-weight:700;line-height:1}
    .bar{height:10px;background:var(--efs-chip);border-radius:999px;overflow:hidden}
    .bar.main{margin:10px 0 8px}
    .bar>span{display:block;height:100%;background:var(--efs-accent);border-radius:999px}
    .btns{display:flex;gap:10px;flex-wrap:wrap}
    .btn{min-height:44px;display:inline-flex;align-items:center;justify-content:center;padding:0 16px;border-radius:12px;font-size:15px;font-weight:600;text-decoration:none;box-sizing:border-box}
    .btn.primary{flex:1;background:var(--efs-accent);color:#fff}
    .btn.secondary{border:1px solid var(--efs-line);color:var(--efs-text)}
    .btn.block{flex:1}
    .foot{border-top:1px solid var(--efs-line);padding-top:10px}
    ul{list-style:none;margin:0;padding:0}
    .agenda li{display:flex;align-items:center;gap:14px;padding:10px 0;border-top:1px solid var(--efs-line)}
    .agenda li:first-child{border-top:0;padding-top:0}
    .d{width:54px;flex:none;text-align:center;padding:5px 0;border-radius:10px;background:var(--efs-soft)}
    .d small{display:block;font-size:11px;font-weight:600;text-transform:uppercase;color:var(--efs-muted)}
    .d strong{display:block;font-size:21px;line-height:1.1}
    .d em{display:block;font-style:normal;font-size:11px;font-weight:700;text-transform:uppercase;color:var(--efs-accent-text)}
    .who{flex:1;min-width:0}
    .who b{display:block;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .who span{display:block;font-size:13px;color:var(--efs-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .st{width:120px;flex:none;display:flex;flex-direction:column;align-items:flex-end;gap:5px;font-size:14px;font-weight:600}
    .st .bar{width:100%;height:6px}
    .st a{font-size:12px;color:var(--efs-accent-text);text-decoration:none}
    svg.map{display:block;width:100%;height:auto;border-radius:12px}
    .map-bg{fill:var(--efs-map)}.map-grid{stroke:var(--efs-grid);stroke-width:1}
    .map-circle{fill:var(--efs-accent);fill-opacity:.06;stroke:var(--efs-accent);stroke-width:1.5;stroke-dasharray:6 6}
    .map-home{fill:var(--efs-text)}.map-roof{fill:var(--ha-card-background,var(--card-background-color,#fff))}
    .mk-open{fill:var(--efs-accent);stroke:var(--ha-card-background,var(--card-background-color,#fff));stroke-width:2}
    .mk-closed{fill:var(--ha-card-background,var(--card-background-color,#fff));stroke:var(--efs-accent);stroke-width:2.5}
    .mk-full{fill:var(--efs-muted);stroke:var(--ha-card-background,var(--card-background-color,#fff));stroke-width:2}
    .map-label{font-size:12px;font-weight:600;fill:var(--efs-text)}
    .map-small{font-size:12px;fill:var(--efs-muted)}
    .legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:12px;color:var(--efs-muted)}
    .legend span{display:inline-flex;align-items:center;gap:6px}
    .legend svg{flex:none}
    .duo{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:20px;align-items:start}
    svg.gauge{display:block;width:100%;max-width:240px;margin:4px auto 0}
    .gauge-bg{fill:none;stroke:var(--efs-chip);stroke-width:16;stroke-linecap:round}
    .gauge-fg{fill:none;stroke:var(--efs-accent);stroke-width:16;stroke-linecap:round}
    .g-strong{fill:var(--efs-text);font-weight:700}.g-muted{fill:var(--efs-muted)}
    .fill li{display:flex;flex-direction:column;gap:4px;margin-bottom:10px;font-size:13px}
    .fill .bar{height:8px}
    .empty{color:var(--efs-muted);text-align:center;padding:12px}
    .warn{font-size:12px;color:var(--efs-muted)}
  `;

  class EfsCollectesCard extends HTMLElement {
    static getStubConfig() {
      return { vue: "complet", entity: "sensor.efs_prochaine_collecte", agenda_entity: "sensor.efs_collectes_a_venir" };
    }

    setConfig(config) {
      const vues = ["synthese", "agenda", "carte", "complet"];
      if (config.vue && !vues.includes(config.vue)) throw new Error(`vue doit valoir : ${vues.join(", ")}`);
      this._config = {
        vue: "complet",
        entity: "sensor.efs_prochaine_collecte",
        agenda_entity: "sensor.efs_collectes_a_venir",
        max: 6,
        ...config,
      };
      if (!this.shadowRoot) this.attachShadow({ mode: "open" });
      this._sig = null;
      if (this._hass) this._render();
    }

    set hass(hass) {
      this._hass = hass;
      const a = hass.states[this._config?.entity];
      const b = hass.states[this._config?.agenda_entity];
      const sig = `${a?.last_updated}|${b?.last_updated}|${new Date().getDate()}|${hass.themes?.darkMode}`;
      if (sig !== this._sig) {
        this._sig = sig;
        this._render();
      }
    }

    getCardSize() {
      return { synthese: 6, agenda: 7, carte: 9 }[this._config?.vue] || 20;
    }

    getGridOptions() {
      return { columns: 12, min_columns: 6 };
    }

    // ------------------------------------------------------------- données
    _data() {
      const hass = this._hass;
      const tz = hass.config?.time_zone || TZ_FALLBACK;
      const next = hass.states[this._config.entity];
      const ag = hass.states[this._config.agenda_entity];
      const A = next?.attributes || {};
      const G = ag?.attributes || {};
      const list = (G.collectes || []).map((c) => ({
        ...c,
        debutDate: new Date(c.debut),
        places_restantes: num(c.places_restantes),
        places_totales: num(c.places_totales),
        taux: num(c.taux_remplissage),
        statut: c.statut || statutDe(num(c.places_restantes)),
      }));
      const debut = next && !["unknown", "unavailable"].includes(next.state) ? new Date(next.state) : null;
      return {
        tz, next, ag, A, G, list, debut,
        restantes: num(A.places_restantes),
        totales: num(A.places_totales),
        reservees: num(A.places_reservees),
        taux: num(A.taux_remplissage),
        nb: num(ag?.state),
      };
    }

    _fmt(tz) {
      return {
        long: new Intl.DateTimeFormat("fr-FR", { timeZone: tz, weekday: "long", day: "numeric", month: "long" }),
        wd: new Intl.DateTimeFormat("fr-FR", { timeZone: tz, weekday: "short" }),
        day: new Intl.DateTimeFormat("fr-FR", { timeZone: tz, day: "numeric" }),
        mon: new Intl.DateTimeFormat("fr-FR", { timeZone: tz, month: "short" }),
        short: new Intl.DateTimeFormat("fr-FR", { timeZone: tz, day: "2-digit", month: "2-digit" }),
        time: new Intl.DateTimeFormat("fr-FR", { timeZone: tz, hour: "2-digit", minute: "2-digit" }),
        ymd: new Intl.DateTimeFormat("en-CA", { timeZone: tz }),
      };
    }

    _days(date, f) {
      const a = Date.parse(f.ymd.format(new Date()) + "T12:00:00Z");
      const b = Date.parse(f.ymd.format(date) + "T12:00:00Z");
      const n = Math.round((b - a) / 864e5);
      return n <= 0 ? "aujourd’hui" : n === 1 ? "demain" : `dans ${n} jours`;
    }

    // -------------------------------------------------------------- rendu
    _render() {
      if (!this._config || !this._hass || !this.shadowRoot) return;
      const d = this._data();
      let body;
      if (!d.next || !d.ag) {
        body = `<div class="empty">Entités introuvables : ${esc(this._config.entity)} / ${esc(this._config.agenda_entity)}.<br>Vérifiez que l’intégration EFS est installée.</div>`;
      } else {
        const f = this._fmt(d.tz);
        const parts = [];
        const v = this._config.vue;
        if (v === "synthese" || v === "complet") parts.push(this._synthese(d, f));
        if (v === "agenda" || v === "complet") parts.push(this._agenda(d, f));
        if (v === "carte" || v === "complet") parts.push(this._carte(d, f));
        body = parts.map((p) => `<section class="bloc">${p}</section>`).join("");
      }
      const accent = /^#[0-9a-f]{3,8}$/i.test(this._config.couleur || "") ? `--efs-accent:${this._config.couleur};` : "";
      const dark = this._hass.themes?.darkMode ? "dark" : "";
      this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card class="${dark}" style="${accent}">${body}</ha-card>`;
    }

    _synthese(d, f) {
      const A = d.A;
      const don = DON[A.type_don] || DON[d.G.type_don] || "Don du sang";
      if (!d.debut) {
        return `<div class="row"><div class="row left"><div class="icon">${ICON_DROP}</div><span class="h">Don du sang</span></div><span class="chip neutral">${esc(don)}</span></div>
          <div class="empty">Aucune collecte dans les ${esc(d.G.horizon_jours ?? "")} prochains jours à moins de ${esc(d.G.rayon_km ?? "")} km.</div>`;
      }
      const statut = A.statut || statutDe(d.restantes);
      const lien = statut === ST.OUVERT ? safeUrl(A.lien_rdv) : null;
      const centre = d.G.centre;
      const iti = centre && A.latitude
        ? `https://www.openstreetmap.org/directions?route=${centre.latitude}%2C${centre.longitude}%3B${A.latitude}%2C${A.longitude}`
        : null;
      const autres = Math.max(0, (d.nb ?? d.list.length) - 1);
      const maj = A.derniere_mise_a_jour ? `Mis à jour à ${f.time.format(new Date(A.derniere_mise_a_jour))}` : "";
      const places = d.restantes !== null
        ? `<div class="row" style="align-items:baseline"><div><span class="big">${d.restantes}</span> <span class="muted">${d.totales ? `places restantes sur ${d.totales}` : "places restantes"}</span></div>${chip(statut)}</div>
           ${d.taux !== null ? `<div class="bar main" role="img" aria-label="${pct(d.taux)} des places réservées"><span style="width:${Math.min(100, d.taux)}%"></span></div>
           <div class="row muted small"><span>Taux de remplissage ${pct(d.taux)}</span>${d.reservees !== null ? `<span>${d.reservees} réservées</span>` : ""}</div>` : ""}`
        : `<div class="row"><span class="muted">Les rendez-vous ne sont pas encore ouverts.</span>${chip(statut)}</div>`;
      return `
        <div class="row"><div class="row left"><div class="icon">${ICON_DROP}</div><span class="h">Don du sang</span></div><span class="chip neutral">${esc(don)}</span></div>
        <div><div class="kicker">Prochaine collecte · ${this._days(d.debut, f)}</div>
          <div class="date">${esc(f.long.format(d.debut).replace(/^./, (c) => c.toUpperCase()))}</div>
          <div class="muted">${esc(String(A.horaires || "").replace(/-/g, " – ").replace(/ \/ /g, " · "))}</div></div>
        <div class="place">${ICON_PIN}<div><b>${esc([A.lieu, titre(A.commune)].filter(Boolean).join(" · "))}</b>
          <div class="muted small">${esc([A.adresse, km(A.distance)].filter(Boolean).join(" · "))}</div></div></div>
        <div>${places}</div>
        <div class="btns">
          ${lien ? `<a class="btn primary" href="${esc(lien)}" target="_blank" rel="noopener">Prendre rendez-vous</a>`
                 : `<a class="btn secondary block" href="https://dondesang.efs.sante.fr" target="_blank" rel="noopener">Site de l’EFS</a>`}
          ${iti ? `<a class="btn secondary" href="${esc(iti)}" target="_blank" rel="noopener">Itinéraire</a>` : ""}
        </div>
        <div class="row muted xs foot"><span>${esc(maj)}${A.api_disponible === false ? " · API indisponible, données conservées" : ""}</span>
          <span>${autres ? `${autres} autre${autres > 1 ? "s" : ""} collecte${autres > 1 ? "s" : ""} dans ${esc(d.G.rayon_km ?? "")} km` : ""}</span></div>`;
    }

    _agenda(d, f) {
      const max = Math.max(1, Number(this._config.max) || 6);
      const rows = d.list.slice(0, max);
      const head = `<div class="row" style="align-items:baseline"><span class="h">Collectes à venir</span>
        <span class="muted small">${esc(d.nb ?? d.list.length)} · rayon ${esc(d.G.rayon_km ?? "")} km · ${esc(d.G.horizon_jours ?? "")} jours</span></div>`;
      if (!rows.length) return head + `<div class="empty">Aucune collecte dans l’horizon configuré.</div>`;
      const items = rows.map((c) => {
        const lien = safeUrl(c.lien_rdv);
        let right;
        if (c.statut === ST.OUVERT) {
          right = `<span>${c.places_totales ? `${c.places_restantes} / ${c.places_totales}` : `${c.places_restantes} places`}</span>
            ${c.taux !== null ? `<div class="bar"><span style="width:${Math.min(100, c.taux)}%"></span></div>` : ""}
            ${lien ? `<a href="${esc(lien)}" target="_blank" rel="noopener">Rendez-vous</a>` : ""}`;
        } else right = chip(c.statut);
        return `<li><div class="d"><small>${esc(f.wd.format(c.debutDate))}</small><strong>${esc(f.day.format(c.debutDate))}</strong><em>${esc(f.mon.format(c.debutDate))}</em></div>
          <div class="who"><b>${esc(titre(c.commune || c.lieu))}</b><span>${esc([c.lieu, km(c.distance)].filter(Boolean).join(" · "))}</span>
          <span>${esc(String(c.horaires || "").replace(/-/g, " – ").replace(/ \/ /g, " · "))}</span></div>
          <div class="st">${right}</div></li>`;
      }).join("");
      const plus = (d.nb ?? 0) > rows.length ? `<div class="muted xs">+ ${d.nb - rows.length} autres collectes (calendrier « Collectes »)</div>` : "";
      return head + `<ul class="agenda">${items}</ul>` + plus;
    }

    _carte(d, f) {
      const centre = d.G.centre;
      const R = Number(d.G.rayon_km) || 10;
      if (!centre) return `<div class="warn">Carte indisponible : mettez l’intégration à jour (v1.1.0 ou plus).</div>`;
      const W = 512, H = 440, CX = 256, CY = 220, RPX = 190, s = RPX / R;
      const cos = Math.cos((centre.latitude * Math.PI) / 180);
      const P = (lat, lon) => [CX + (lon - centre.longitude) * 111 * cos * s, CY - (lat - centre.latitude) * 111 * s];
      const step = [1, 2, 5, 10, 20, 25, 50].find((v) => R / v <= 3) || 50;
      let grid = "";
      for (let k = -Math.floor(R / step) * step; k <= R; k += step) {
        grid += `<line class="map-grid" x1="${CX + k * s}" y1="0" x2="${CX + k * s}" y2="${H}"/><line class="map-grid" x1="0" y1="${CY + k * s}" x2="${W}" y2="${CY + k * s}"/>`;
      }
      const lieux = new Map();
      for (const c of d.list) {
        if (c.latitude === undefined) continue;
        const k = `${c.lieu}|${c.latitude}|${c.longitude}`;
        if (!lieux.has(k)) lieux.set(k, c);
      }
      const first = d.list[0];
      // Les pastilles occupent aussi de la place : les étiquettes les évitent.
      const placed = [[CX - 12, CX + 12, CY - 12, CY + 12]];
      for (const c of lieux.values()) {
        const [x, y] = P(c.latitude, c.longitude);
        placed.push([x - 12, x + 12, y - 12, y + 12]);
      }
      let marks = "";
      for (const c of lieux.values()) {
        const [x, y] = P(c.latitude, c.longitude);
        const cls = c.statut === ST.OUVERT ? "mk-open" : c.statut === ST.COMPLET ? "mk-full" : "mk-closed";
        const isNext = c === first;
        const label = `${titre(c.commune || c.lieu)} · ${f.short.format(c.debutDate)}${c.statut === ST.COMPLET ? " complet" : ""}`;
        const w = label.length * 6.6;
        const box = (side, ly) => (side ? [x + 14, x + 14 + w] : [x - 14 - w, x - 14]).concat([ly - 11, ly + 3]);
        const hit = (b) => b[0] < 2 || b[1] > W - 2 || placed.some((q) => b[0] < q[1] && q[0] < b[1] && b[2] < q[3] && q[2] < b[3]);
        let right = x + 14 + w < W - 2, ly = y + 4, bx = box(right, ly);
        search: for (const off of [0, 15, -15, 30, -30, 45]) {
          for (const side of [right, !right]) {
            const cand = box(side, y + 4 + off);
            if (!hit(cand)) { right = side; ly = y + 4 + off; bx = cand; break search; }
          }
        }
        placed.push(bx);
        const osm = `https://www.openstreetmap.org/?mlat=${c.latitude}&mlon=${c.longitude}#map=16/${c.latitude}/${c.longitude}`;
        marks += `<a href="${esc(osm)}" target="_blank" rel="noopener"><title>${esc(`${c.lieu} – ${c.places_restantes === null ? "planning non ouvert" : `${c.places_restantes} places restantes`}`)}</title>
          <circle class="${cls}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${isNext ? 11 : 8}" ${isNext ? 'stroke-width="3"' : ""}/>
          <text class="map-label" x="${(right ? x + 14 : x - 14).toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="${right ? "start" : "end"}">${esc(label)}</text></a>`;
      }
      const map = `<svg class="map" viewBox="0 0 ${W} ${H}" role="img" aria-label="Carte des collectes dans un rayon de ${R} km">
        <rect class="map-bg" x="0" y="0" width="${W}" height="${H}"/>${grid}
        <circle class="map-circle" cx="${CX}" cy="${CY}" r="${RPX}"/>
        <text class="map-small" x="${CX}" y="${CY - RPX - 8}" text-anchor="middle">${R} km</text>
        <text class="map-small" x="10" y="${H - 10}">Quadrillage : ${step} km</text>
        <circle class="map-home" cx="${CX}" cy="${CY}" r="9"/><path class="map-roof" d="M${CX - 5} ${CY + 2} L${CX} ${CY - 4} L${CX + 5} ${CY + 2} V${CY + 6} H${CX - 5} Z"/>
        ${marks}</svg>`;
      const dot = (cls) => `<svg width="12" height="12" aria-hidden="true"><circle cx="6" cy="6" r="4.5" class="${cls}"/></svg>`;

      const cible = d.list.find((c) => c.taux !== null);
      let gauge = `<div><span class="h">Remplissage</span><div class="empty">Aucune collecte au planning ouvert.</div></div>`;
      if (cible) {
        const p = Math.max(0, Math.min(100, cible.taux)) / 100;
        const a = Math.PI - p * Math.PI;
        const gx = (100 + 80 * Math.cos(a)).toFixed(1), gy = (100 - 80 * Math.sin(a)).toFixed(1);
        gauge = `<div><span class="h">Remplissage · ${esc(titre(cible.commune || cible.lieu))}</span>
          <div class="muted small">${esc(f.long.format(cible.debutDate))} · prochaine collecte aux rendez-vous ouverts</div>
          <svg class="gauge" viewBox="0 0 200 116" role="img" aria-label="${pct(cible.taux)} des places réservées">
            <path class="gauge-bg" d="M20 100 A80 80 0 0 1 180 100"/>${p > 0 ? `<path class="gauge-fg" d="M20 100 A80 80 0 0 1 ${gx} ${gy}"/>` : ""}
            <text x="100" y="92" text-anchor="middle" font-size="30" class="g-strong">${pct(cible.taux)}</text>
            <text x="100" y="112" text-anchor="middle" font-size="11" class="g-muted">${cible.places_totales ? `${cible.places_totales - cible.places_restantes} réservées / ${cible.places_totales}` : ""}</text></svg></div>`;
      }
      const remplies = d.list.filter((c) => c.taux !== null).slice(0, 6);
      const fill = `<div><div class="row" style="align-items:baseline"><span class="h">Places réservées par collecte</span></div>
        ${remplies.length ? `<ul class="fill" style="margin-top:10px">${remplies.map((c) => `<li>
          <div class="row"><span>${esc(f.short.format(c.debutDate))} · ${esc(titre(c.commune || c.lieu))}</span><span class="muted">${c.places_totales ? `${c.places_restantes} / ${c.places_totales} libres` : pct(c.taux)}</span></div>
          <div class="bar"><span style="width:${Math.min(100, c.taux)}%"></span></div></li>`).join("")}</ul>`
          : `<div class="empty">Les compteurs apparaîtront à l’ouverture des plannings.</div>`}</div>`;

      return `<div class="row" style="align-items:baseline"><span class="h">Collectes dans un rayon de ${esc(R)} km</span><span class="muted small">${lieux.size} lieu${lieux.size > 1 ? "x" : ""}</span></div>
        ${map}
        <div class="legend"><span>${dot("mk-open")}Planning ouvert</span><span>${dot("mk-closed")}Non ouvert</span><span>${dot("mk-full")}Complet</span></div>
        <div class="duo">${gauge}${fill}</div>`;
    }
  }

  if (!customElements.get("efs-collectes-card")) {
    customElements.define("efs-collectes-card", EfsCollectesCard);
    window.customCards = window.customCards || [];
    window.customCards.push({
      type: "efs-collectes-card",
      name: "EFS – Collectes de don du sang",
      description: "Prochaine collecte, agenda, carte et remplissage (intégration efs_dondesang).",
      preview: true,
    });
    console.info(`%c EFS-COLLECTES-CARD %c v${VERSION} `, "background:#B42318;color:#fff", "");
  }
})();
