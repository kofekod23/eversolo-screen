"use strict";
/* Écran de lecture : relève /api/state chaque seconde, rend l'état, anime
   les changements. Horloge de rendu à 4 Hz (suffisant pour une barre de
   progression, léger pour un Raspberry Pi). */

const $ = id => document.getElementById(id);
const I18N = {
  fr: { maj: "Mise à jour", maj_telechargement: "téléchargement", maj_verification: "vérification de la signature", maj_installation: "installation", playing: "En lecture", paused: "Pause", stopped: "Arrêté", waiting: "Eversolo en veille", offline: "Streamer introuvable sur le réseau", live: "En direct", muted: "Muet", volume: "Volume", next: "Ensuite", last: "Dernière écoute", hires: "Hi-Res", cd: "Qualité CD", hintArtist: "SUIV : album   VOL : défiler   INFO : fermer", hintAlbum: "SUIV : production   PRÉC : artiste   INFO : fermer", hintProd: "PRÉC : album   VOL : défiler   INFO : fermer", tracksSec: "Plages", prodSec: "Production", noAlbum: "Aucune information trouvée pour ce disque.", noProd: "Aucun crédit de production trouvé pour cette édition.", loading: "Chargement…" },
  en: { maj: "Update", maj_telechargement: "downloading", maj_verification: "checking the signature", maj_installation: "installing", playing: "Now playing", paused: "Paused", stopped: "Stopped", waiting: "Eversolo on standby", offline: "Streamer not found on the network", live: "Live", muted: "Muted", volume: "Volume", next: "Up next", last: "Last played", hires: "Hi-Res", cd: "CD quality", hintArtist: "NEXT: album   VOL: scroll   INFO: close", hintAlbum: "NEXT: production   PREV: artist   INFO: close", hintProd: "PREV: album   VOL: scroll   INFO: close", tracksSec: "Tracks", prodSec: "Production", noAlbum: "No information found for this record.", noProd: "No production credits found for this edition.", loading: "Loading…" },
  es: { maj: "Actualización", maj_telechargement: "descarga", maj_verification: "verificación de la firma", maj_installation: "instalación", playing: "Reproduciendo", paused: "Pausa", stopped: "Detenido", waiting: "Eversolo en espera", offline: "Streamer no encontrado en la red", live: "En directo", muted: "Silencio", volume: "Volumen", next: "A continuación", last: "Última escucha", hires: "Hi-Res", cd: "Calidad CD", hintArtist: "SIG: álbum   VOL: desplazar   INFO: cerrar", hintAlbum: "SIG: producción   ANT: artista   INFO: cerrar", hintProd: "ANT: álbum   VOL: desplazar   INFO: cerrar", tracksSec: "Pistas", prodSec: "Producción", noAlbum: "No se encontró información de este disco.", noProd: "No se encontraron créditos de producción de esta edición.", loading: "Cargando…" },
  de: { maj: "Update", maj_telechargement: "Download", maj_verification: "Signaturprüfung", maj_installation: "Installation", playing: "Wiedergabe", paused: "Pause", stopped: "Gestoppt", waiting: "Eversolo im Standby", offline: "Streamer im Netzwerk nicht gefunden", live: "Live", muted: "Stumm", volume: "Lautstärke", next: "Als Nächstes", last: "Zuletzt gehört", hires: "Hi-Res", cd: "CD-Qualität", hintArtist: "WEITER: Album   VOL: blättern   INFO: schließen", hintAlbum: "WEITER: Produktion   ZURÜCK: Künstler   INFO: schließen", hintProd: "ZURÜCK: Album   VOL: blättern   INFO: schließen", tracksSec: "Titel", prodSec: "Produktion", noAlbum: "Keine Informationen zu diesem Album gefunden.", noProd: "Keine Produktions-Credits zu dieser Ausgabe gefunden.", loading: "Wird geladen…" }
};

const DECOUVERTE_MS = 9000;    // durée d'une fiche
const OSD_MS = 2200;           // volume affiché après un réglage
const DECALAGE_MS = 180000;    // protection : décalage toutes les 3 min
const ATTENUE_MS = 600000;     // 10 min sans lecture
const NOIR_MS = 1800000;       // 30 min sans lecture
const ENSUITE_AVANT_FIN = 20;  // secondes
const TEINTE_NEUTRE = [210, 8];

let L = I18N.fr;
let langue = "fr";
let state = null;
let receivedAt = 0;
let lastCover = null;
let revInitiale = null;
let coverTitle = null;
let titreAffiche = null;
let derniereEcoute = null;
let volPrecedent = null;
let osdTimer = null;
let calmeDepuis = performance.now();
let panelVisible = false;
// Crans de défilement que permet le texte du volet, mesurés au moment de
// chaque relevé : la photo et les polices peuvent allonger le texte après
// le dessin.
function cransVolet() {
  const wrapEl = $("p_wrap"), txt = $("p_text");
  const cran = wrapEl.clientHeight * 0.6;
  const max = Math.max(0, txt.scrollHeight - wrapEl.clientHeight);
  return cran > 0 ? Math.ceil(max / cran) : 0;
}
let reglages = { theme: "pochette", profil: "salon", nuit: "auto", nuit_debut: 22, nuit_fin: 7, protection: true };

function fmt(s) {
  s = Math.max(0, Math.floor(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}
function texte(id, valeur) {
  const el = $(id);
  const v = valeur == null ? "" : String(valeur);
  if (el.textContent !== v) el.textContent = v;
}
function relancer(el, classe) {
  el.classList.remove(classe);
  void el.offsetWidth;
  el.classList.add(classe);
}

const RELEVE_MAX_MS = 4000;     // délai maximal d'un relevé
const RATES_TOLERES = 3;        // relevés manqués avant d'afficher « introuvable »
let rates = 0;

async function relever() {
  const arret = new AbortController();
  const minuteur = setTimeout(() => arret.abort(), RELEVE_MAX_MS);
  try {
    // Volet ouvert : le serveur apprend où s'arrête le texte, pour ne pas
    // compter des crans de défilement au-delà de la fin.
    const url = panelVisible ? `/api/state?volet_pas=${cransVolet()}` : "/api/state";
    const r = await fetch(url, { cache: "no-store", signal: arret.signal });
    return await r.json();
  } finally {
    clearTimeout(minuteur);
  }
}

async function poll() {
  let recu;
  try {
    recu = await relever();
    rates = 0;
  } catch (e) {
    rates += 1;
    if (state && rates < RATES_TOLERES) return;  // un raté isolé ne vide pas l'écran
    recu = { connected: false };
  }
  if (recu.setup) { location = "/setup"; return; }
  if (recu.lang && I18N[recu.lang]) {
    L = I18N[recu.lang]; langue = recu.lang; document.documentElement.lang = langue;
  }
  if (recu.display) reglages = recu.display;
  if (recu.rev) {
    // nouvelle version installée : on recharge, même au repos
    if (revInitiale === null) revInitiale = recu.rev;
    else if (recu.rev !== revInitiale) { location.reload(); return; }
  }
  state = recu;
  receivedAt = performance.now();
  try { render(); } catch (e) { console.error("rendu :", e); }
}

/* ---------------- Teinte tirée de la pochette ---------------- */
function teinteDe(img) {
  try {
    const c = document.createElement("canvas");
    c.width = c.height = 28;
    const x = c.getContext("2d", { willReadFrequently: true });
    x.drawImage(img, 0, 0, 28, 28);
    const d = x.getImageData(0, 0, 28, 28).data;
    const bacs = Array.from({ length: 18 }, () => ({ poids: 0, h: 0, s: 0 }));
    for (let i = 0; i < d.length; i += 4) {
      const r = d[i] / 255, g = d[i + 1] / 255, b = d[i + 2] / 255;
      const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2, ec = max - min;
      if (ec < 0.1 || l < 0.1 || l > 0.93) continue;
      const s = ec / (1 - Math.abs(2 * l - 1));
      let h = max === r ? ((g - b) / ec) % 6 : max === g ? (b - r) / ec + 2 : (r - g) / ec + 4;
      h = (h * 60 + 360) % 360;
      const bac = bacs[Math.floor(h / 20) % 18];
      const p = s * s * (1 - Math.abs(l - 0.5));
      bac.poids += p; bac.h += h * p; bac.s += s * p;
    }
    const m = bacs.reduce((a, b) => (b.poids > a.poids ? b : a));
    if (m.poids < 5) return TEINTE_NEUTRE;  // pochette presque grise
    return [Math.round(m.h / m.poids), Math.round(Math.min(80, Math.max(30, (m.s / m.poids) * 100)))];
  } catch (e) {
    return TEINTE_NEUTRE;
  }
}
function appliquerTeinte([h, s]) {
  const r = document.documentElement.style;
  r.setProperty("--h", h);
  r.setProperty("--s", s);
}

/* ---------------- Volet infos ---------------- */
function remplirFaits(conteneur, faits) {
  conteneur.textContent = "";
  (faits || []).forEach(f => {
    const el = document.createElement("span");
    el.textContent = f;
    conteneur.appendChild(el);
  });
}
function montrerImage(im, src) {
  if (!src) { im.style.display = "none"; im.dataset.src = ""; return; }
  if (im.dataset.src === src) return;
  im.dataset.src = src;
  im.onload = () => { im.style.display = "block"; };
  im.onerror = () => { im.style.display = "none"; };
  im.src = src;
}
function cleTitre(t) {
  return String(t || "").toLowerCase().replace(/\s*[\(\[].*?[\)\]]/g, "").replace(/[^\p{L}\p{N}]+/gu, " ").trim();
}
function ligne(cls, valeurs) {
  const row = document.createElement("div");
  if (cls) row.className = cls;
  valeurs.forEach(([c, v]) => {
    const sp = document.createElement("span"); sp.className = c; sp.textContent = v || ""; row.appendChild(sp);
  });
  return row;
}

function fermerVolet() {
  $("panel").classList.remove("on");
  $("dimmer").classList.remove("on");
  panelVisible = false;
  voletCle = "";
}

let voletCle = "";
function renderPanel(s) {
  const p = s.panel;
  const on = !!(p && (p.artist || p.text));
  if (!on) { fermerVolet(); return; }
  $("panel").classList.add("on");
  $("dimmer").classList.add("on");
  panelVisible = true;
  // Relevé toutes les 300 ms volet ouvert : on ne reconstruit que si le contenu change.
  const cle = JSON.stringify(p) + s.title + langue;
  if (cle === voletCle) return;
  voletCle = cle;
  const page = p.page || "artist";
  const art = p.artist || {};
  const alb = p.album;
  $("t_wrap").hidden = true;
  $("c_wrap").hidden = true;
  if (page === "artist") {
    texte("p_name", art.name);
    remplirFaits($("p_facts"), art.facts);
    texte("b_text", art.text);
    texte("p_src", art.source);
    texte("p_hint", L.hintArtist);
    montrerImage($("p_img"), art.image);
  } else if (page === "album") {
    texte("p_name", alb ? alb.title : "");
    remplirFaits($("p_facts"), alb ? alb.facts : []);
    texte("b_text", alb ? alb.text : L.noAlbum);
    const tracks = (alb && alb.tracks) || [];
    if (tracks.length) {
      $("t_wrap").hidden = false;
      texte("t_label", L.tracksSec);
      const ici = cleTitre(s.title);
      $("t_list").replaceChildren(...tracks.map(t =>
        ligne(ici && cleTitre(t.title) === ici ? "ici" : "", [["tn", t.n], ["tt", t.title], ["td", t.dur]])));
    }
    texte("p_src", alb && alb.source);
    texte("p_hint", L.hintAlbum);
    montrerImage($("p_img"), alb ? ($("cover").src || null) : null);
  } else {
    texte("p_name", alb && alb.title);
    remplirFaits($("p_facts"), (alb && alb.prod_facts) || []);
    const credits = (alb && alb.credits) || [];
    texte("b_text", credits.length ? "" : (alb && alb.loading ? L.loading : L.noProd));
    if (credits.length) {
      $("c_wrap").hidden = false;
      texte("c_label", L.prodSec);
      $("c_list").replaceChildren(...credits.map(c => ligne("", [["cr", c.role], ["cn", c.name]])));
    }
    texte("p_src", alb && alb.source);
    texte("p_hint", L.hintProd);
    montrerImage($("p_img"), alb ? ($("cover").src || null) : null);
  }

  requestAnimationFrame(() => {
    const wrapEl = $("p_wrap"), txt = $("p_text");
    const max = Math.max(0, txt.scrollHeight - wrapEl.clientHeight);
    const off = Math.min((p.scroll || 0) * wrapEl.clientHeight * 0.6, max);
    txt.style.transform = `translateY(${-off}px)`;
    const debord = max > 4;
    $("p_fade").style.opacity = debord && off < max ? "1" : "0";
    $("p_rail").style.opacity = debord ? "1" : "0";
    const railH = wrapEl.clientHeight;
    $("p_thumb").style.top = (max > 0 ? (off / max) * (railH * 0.75) : 0) + "px";
  });
}

/* ---------------- Signal, volume, découvertes ---------------- */
function renderSignal(sig) {
  const el = $("signal");
  const cle = JSON.stringify(sig || {}) + langue;
  if (el.dataset.cle === cle) return;
  el.dataset.cle = cle;
  const morceaux = [];
  if (sig && sig.format) { const f = document.createElement("span"); f.className = "fmt"; f.textContent = sig.format; morceaux.push(f); }
  [sig && sig.resolution, sig && sig.debit].filter(Boolean).forEach(t => {
    const sp = document.createElement("span"); sp.textContent = t; morceaux.push(sp);
  });
  const libelle = sig && { hires: L.hires, cd: L.cd }[sig.classe];
  if (libelle) {
    const c = document.createElement("span");
    c.className = "classe " + sig.classe;
    c.textContent = libelle;
    morceaux.push(c);
  }
  el.replaceChildren(...morceaux);
}

function renderVolume(v) {
  $("volmini").hidden = !v;
  if (!v) { volPrecedent = null; return; }
  $("volmini").classList.toggle("muet", v.muet);
  texte("voltexte", v.texte);
  $("volbarre").style.transform = `scaleX(${v.pct / 100})`;
  texte("muetBadge", L.muted);
  const cle = `${v.texte}|${v.muet}`;
  if (volPrecedent !== null && volPrecedent !== cle) montrerOsd(v);
  volPrecedent = cle;
}
function montrerOsd(v) {
  const osd = $("osd");
  texte("osdK", L.volume);
  texte("osdV", v.muet ? L.muted : v.texte);
  $("osdJ").style.transform = `scaleX(${v.muet ? 0 : v.pct / 100})`;
  osd.classList.toggle("muet", v.muet);
  osd.classList.add("on");
  clearTimeout(osdTimer);
  osdTimer = setTimeout(() => osd.classList.remove("on"), OSD_MS);
  calmeDepuis = performance.now();
}

let fiches = [];
let ficheIndex = -1;
let ficheCle = "";
let ficheGeneration = 0;
function renderDecouvertes(liste) {
  const cle = JSON.stringify(liste || []);
  if (cle === ficheCle) return;
  const premiere = !fiches.length;
  fiches = liste || [];
  ficheCle = cle;
  ficheGeneration += 1;
  $("decouverte").classList.toggle("on", fiches.length > 0);
  if (premiere || ficheIndex >= fiches.length) { ficheIndex = -1; tournerFiche(true); }
}
function tournerFiche(immediat) {
  if (!fiches.length) return;
  ficheIndex = (ficheIndex + 1) % fiches.length;
  const f = fiches[ficheIndex];
  if (immediat) { texte("dk", f.k); texte("dv", f.v); return; }
  if (fiches.length === 1 && $("dv").textContent === f.v) return;
  const el = $("fiche");
  const generation = ficheGeneration;
  el.classList.add("sort");
  setTimeout(() => {
    if (generation !== ficheGeneration) { el.classList.remove("sort"); return; }  // liste changée entre-temps
    texte("dk", f.k); texte("dv", f.v);
    el.classList.remove("sort"); el.classList.add("entre");
    void el.offsetWidth;
    el.classList.remove("entre");
  }, 360);
}
setInterval(() => { if (!document.hidden) tournerFiche(false); }, DECOUVERTE_MS);

function initiales(s) {
  const base = (s.album || s.title || "").replace(/[\(\[].*$/, "").trim();
  const mots = base.split(/\s+/).filter(m => /\p{L}|\p{N}/u.test(m));
  return mots.slice(0, 2).map(m => [...m.replace(/^[^\p{L}\p{N}]+/u, "")][0] || "").join("").toUpperCase();
}

/* ---------------- Rendu principal ---------------- */
function render() {
  const s = state;
  document.body.dataset.theme = reglages.theme || "pochette";
  document.body.dataset.profil = reglages.profil || "salon";
  const maj = s && s.maj;
  $("majBandeau").classList.toggle("on", !!maj);
  if (maj) texte("majBandeau", `${L.maj} : ${L["maj_" + maj.etape] || ""} (${maj.version || ""})`);
  const hasTrack = s && s.connected && s.title;

  $("idle").classList.toggle("on", !hasTrack);
  if (!hasTrack) {
    fermerVolet();
    $("stage").classList.add("pause", "arret");
    $("ensuite").classList.remove("on");
    texte("idleMsg", s && s.connected ? L.waiting : L.offline);
    texte("derniere", derniereEcoute ? `${L.last} : ${derniereEcoute}` : "");
    renderVolume(s && s.volume);
    return;
  }
  derniereEcoute = s.artist ? `${s.title}, ${s.artist}` : s.title;

  const etat = s.etat || (s.playing ? "lecture" : "pause");
  const stage = $("stage");
  stage.classList.toggle("pause", etat !== "lecture");
  stage.classList.toggle("arret", etat === "arret");
  stage.classList.toggle("direct", !!s.live);
  if (etat === "lecture") calmeDepuis = performance.now();
  texte("status", s.live && etat === "lecture" ? L.live : { lecture: L.playing, pause: L.paused, arret: L.stopped }[etat]);
  texte("source", s.signal && s.signal.source);

  try { renderPanel(s); } catch (e) { console.error("volet :", e); }

  if (s.model) texte("model", s.model);
  if (s.title !== titreAffiche) {
    if (titreAffiche !== null) relancer($("meta"), "relance");
    titreAffiche = s.title;
  }
  texte("title", s.title);
  texte("artist", s.artist);
  texte("album", s.album);
  renderSignal(s.signal);
  renderVolume(s.volume);
  renderDecouvertes(s.decouvertes);

  const ensuite = s.ensuite && !s.live;
  if (ensuite) {
    texte("ensuiteK", L.next);
    texte("ensuiteV", s.ensuite.artist ? `${s.ensuite.title}, ${s.ensuite.artist}` : s.ensuite.title);
  }
  $("ensuite").dataset.pret = ensuite ? "1" : "";
  renderCover(s);
}

function renderCover(s) {
  const ph = $("placeholder");
  texte("placeholder", initiales(s));
  if (s.cover && s.cover !== lastCover) {
    // Préchargement invisible puis échange : la pochette actuelle reste
    // affichée tant que la nouvelle n'est pas prête, aucun clignotement.
    lastCover = s.cover;
    const voulue = s.cover;
    const sonde = new Image();
    sonde.onload = () => {
      if (lastCover !== voulue) return;
      const img = $("cover");
      img.classList.remove("on");
      void img.offsetWidth;
      img.src = voulue;
      img.classList.add("on");
      ph.classList.remove("on");
      appliquerTeinte(teinteDe(sonde));
      coverTitle = s.title;
    };
    sonde.onerror = () => {
      // échec passager (CDN, réseau) : on garde l'ancienne image et on
      // retentera dans quelques secondes
      if (!$("cover").classList.contains("on")) ph.classList.add("on");
      setTimeout(() => { if (lastCover === voulue) lastCover = null; }, 5000);
    };
    sonde.src = voulue;
  } else if (!s.cover && s.title !== coverTitle) {
    // nouveau morceau réellement sans pochette : visuel de remplacement
    lastCover = null;
    coverTitle = s.title;
    $("cover").classList.remove("on");
    ph.classList.add("on");
    appliquerTeinte(TEINTE_NEUTRE);
  }
}

/* ---------------- Horloge de rendu, nuit, protection ---------------- */
function estNuit(maintenant) {
  if (reglages.nuit === "toujours") return true;
  if (reglages.nuit !== "auto") return false;
  const h = maintenant.getHours(), d = reglages.nuit_debut, f = reglages.nuit_fin;
  if (d === f) return false;
  return d < f ? (h >= d && h < f) : (h >= d || h < f);
}

let dernierDecalage = performance.now();
function protection(maintenantMs) {
  const actif = reglages.protection !== false;
  const calme = maintenantMs - calmeDepuis;
  document.body.classList.toggle("attenue", actif && calme > ATTENUE_MS && !panelVisible);
  document.body.classList.toggle("noir", actif && calme > NOIR_MS && !panelVisible);
  if (!actif) {
    $("stage").style.transform = "";
    $("idle").style.transform = "";
    return;
  }
  if (maintenantMs - dernierDecalage > DECALAGE_MS) {
    dernierDecalage = maintenantMs;
    const dx = Math.round(Math.random() * 12 - 6), dy = Math.round(Math.random() * 8 - 4);
    $("stage").style.transform = `translate(${dx}px, ${dy}px)`;
    $("idle").style.transform = `translate(${dx * 2}px, ${dy * 2}px)`;
  }
}

const deux = n => String(n).padStart(2, "0");
function horloge(now) {
  texte("clock", deux(now.getHours()) + ":" + deux(now.getMinutes()));
  const gh = $("grandeHeure");
  const cle = deux(now.getHours()) + deux(now.getMinutes()) + langue;
  if (gh.dataset.h === cle) return;
  gh.dataset.h = cle;
  const sep = document.createElement("span");
  sep.textContent = ":";
  gh.replaceChildren(deux(now.getHours()), sep, deux(now.getMinutes()));
  let jour = "";
  try { jour = new Intl.DateTimeFormat(langue, { weekday: "long", day: "numeric", month: "long" }).format(now); } catch (e) { /* langue inconnue */ }
  texte("date", jour);
}

function tick() {
  const maintenantMs = performance.now();
  const s = state;
  if (s && s.connected && s.title) {
    if (s.live) {
      texte("pos", "");
      texte("reste", L.live);
      $("ensuite").classList.remove("on");
    } else if (s.duration > 0) {
      let pos = s.position;
      if (s.etat === "lecture" || (!s.etat && s.playing)) pos += (maintenantMs - receivedAt) / 1000;
      pos = Math.min(pos, s.duration);
      const frac = pos / s.duration;
      $("glow").style.transform = `scaleX(${frac})`;
      $("rail").style.transform = `translateX(${frac * 100}%)`;
      texte("pos", fmt(pos));
      texte("reste", "−" + fmt(s.duration - pos));
      const fin = s.duration - pos < ENSUITE_AVANT_FIN;
      $("ensuite").classList.toggle("on", fin && $("ensuite").dataset.pret === "1");
    } else {
      texte("pos", ""); texte("reste", "");
      $("ensuite").classList.remove("on");
      $("glow").style.transform = "scaleX(0)";
      $("rail").style.transform = "translateX(0)";
    }
  }
  const now = new Date();
  horloge(now);
  document.body.classList.toggle("nuit", estNuit(now));
  protection(maintenantMs);
}

document.addEventListener("mousemove", () => {
  document.body.classList.add("pointer");
  calmeDepuis = performance.now();
  clearTimeout(window._curseur);
  window._curseur = setTimeout(() => document.body.classList.remove("pointer"), 3000);
});

(function boucle() {
  Promise.resolve(poll()).finally(() => setTimeout(boucle, panelVisible ? 300 : 1000));
})();
tick();
setInterval(tick, 250);
