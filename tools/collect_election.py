#!/usr/bin/env python3
"""Election results collector: MySPRSemak (SPR) - latest election per category.

The site (mysprsemak.spr.gov.my) is a Laravel app. Each page embeds a CSRF
token and UUID ids; results come from JSON POSTs:

  GET  /semakan/keputusan/pru       -> _token, state UUIDs, PRU tabs (data-href)
  POST /semakan/keputusan/pru/getParDun       {_token, RefNegeriId, PilihanrayaId}
  POST /semakan/keputusan/keputusanPru        {_token, kategori:PRU, PilihanrayaId,
                                                kodbahagian, DunId, RefNegeriId}
  GET  /semakan/keputusan/pru-dun   -> _token, DUN election options (data-negeri
                                       + value) in #PruDun
  POST /semakan/keputusan/senaraiDunPruDun    {_token, PilihanrayaId, RefNegeriId}
  POST /semakan/keputusan/keputusanPruDun     {_token, kategori:PRU_DUN, PilihanrayaId,
                                                RefNegeriId, kodbahagian:AppendKod}
  GET  /semakan/keputusan/prk       -> _token, PRK tabs (data-uuid)
  POST /semakan/keputusan/keputusanPrk        {_token, kategori:PRK, PilihanrayaId}

"Latest only" scope (user decision):
  - PRU:  the latest parliamentary election (PRU KE-15, 2022) - all states
  - DUN:  the latest state election (Negeri Sembilan KE-16, 2026) - its seats
  - PRK:  the latest by-election (first tab, no year suffix)

Session hygiene: the CSRF token and session cookies are fetched fresh each
run; the token is per-page, so the page for each category is re-fetched
before its POSTs (same session/cookie jar). Polite pacing (0.3s) between
requests. One seat = one request; PRU-15 is 222 seats, DUN 36, PRK 1 - a
one-time backfill of ~260 requests, results do not change.

Writes public/election.json -> KV key `election`:
  { generated, categories: { pru, dun, prk }, seats: [...] }
Every seat: { category, election, state, code, name, date,
              totalVotes, spoiled, majority,
              candidates: [{ name, party, partyShort, colour, votes, status, isWinner }] }
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import http.cookiejar
from datetime import date

BASE = "https://mysprsemak.spr.gov.my"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
      "Accept": "application/json, text/javascript, */*; q=0.01",
      "X-Requested-With": "XMLHttpRequest"}
OUT = os.path.join(os.path.dirname(__file__), "..", "public", "election.json")

POLL = 0.3  # seconds between requests - be polite to a gov server
MAX_FAILS = 25  # consecutive failures before aborting
LIMIT = int(os.environ.get("ELE_LIMIT", "0"))  # test limit: seats per category (0 = all)


def make_opener():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    return op, cj


def get(op, path):
    h = dict(UA)
    req = urllib.request.Request(BASE + path, headers=h)
    with op.open(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def post(op, path, data, referer):
    h = dict(UA)
    h["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    h["Referer"] = BASE + referer
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(BASE + path, data=body, headers=h)
    with op.open(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def token_of(html):
    m = re.search(r'name="_token"\s+value="([^"]+)"', html) or \
        re.search(r'"_token"\s*:\s*"([^"]+)"', html)
    if not m:
        raise ValueError("CSRF token not found - site layout changed?")
    return m.group(1)


def parse_result(j, category):
    """Normalise one seat's result JSON into the output seat object."""
    pr = (j.get("pilihanraya") or [{}])[0]
    cands_raw = pr.get("penamaan") or []
    winner = j.get("penamaanMenang") or {}
    seats_out = []
    cands = []
    for c in cands_raw:
        party = c.get("parti") or {}
        cands.append({
            "name": c.get("NamaUndiCalon"),
            "party": party.get("Penerangan"),
            "partyShort": party.get("NamaSingkatan"),
            "colour": party.get("WarnaParti") or "#888888",
            "votes": _num(c.get("BilUndi")),
            "isWinner": c.get("StatusCalon") == "MNG",
        })
    # if the JSON has the winner but penamaan was empty, add it
    if not cands and winner:
        party = winner.get("parti") or {}
        cands.append({
            "name": winner.get("NamaUndiCalon"),
            "party": party.get("Penerangan"),
            "partyShort": party.get("NamaSingkatan"),
            "colour": party.get("WarnaParti") or "#888888",
            "votes": _num(winner.get("BilUndi")),
            "isWinner": True,
        })
    total = sum(c["votes"] or 0 for c in cands)
    # majority = winner's votes - runner-up's
    votes = sorted((c["votes"] or 0) for c in cands)
    majority = votes[-1] - votes[-2] if len(votes) >= 2 else votes[-1] if votes else None
    seat = {
        "category": category,
        "election": pr.get("NamaSingkatan") or j.get("namaDun") or j.get("namaParDun"),
        "date": pr.get("TarikhPengundian"),
        "name": (j.get("namaParDun") or j.get("namaDun") or "").strip(),
        "state": (j.get("RefNegeriId") or ""),
        "totalVotes": total,
        "majority": majority,
        "candidates": cands,
    }
    # state name: RefNegeriId is a UUID; resolve via the states map later
    return seat


def _num(s):
    if s is None:
        return None
    try:
        return int(re.sub(r"[^0-9]", "", s))
    except ValueError:
        return None


def main():
    op, _ = make_opener()
    fails = 0
    seats = []
    states = []
    pru_id = None  # set by the PRU crawl; needed for PRU-embedded DUN seats
    meta = {"pru": None, "dun": None, "prk": None}
    meta.setdefault("pru"); meta.setdefault("dun"); meta.setdefault("prk")

    # ── PRU (latest parliamentary election) ────────────────────────────
    try:
        html = get(op, "/semakan/keputusan/pru")
        token = token_of(html)
        states = re.findall(r'<option id="([A-F0-9-]{36})"[^>]*name="negeriOption"[^>]*>\s*([A-Z ]+)</option>', html)
        pru_tabs = re.findall(r'data-href="([A-F0-9-]{36})"[^>]*>\s*(?:<i[^>]*></i>\s*)?([^<]{3,60})', html, re.S)
        if not pru_tabs:
            raise ValueError("PRU tabs not found")
        pru_id, pru_name = pru_tabs[0][0], pru_tabs[0][1].strip()
        meta["pru"] = {"id": pru_id, "name": pru_name}
        sys.stderr.write(f"PRU: {pru_name} ({len(states)} states)\n")
        for state_id, state_name in states:
            d = json.loads(post(op, "/semakan/keputusan/pru/getParDun",
                                {"_token": token, "RefNegeriId": state_id,
                                 "PilihanrayaId": pru_id},
                                "/semakan/keputusan/pru"))
            pars = d.get("parlimen") or []
            if LIMIT and LIMIT > 0:
                pars = pars[:LIMIT]
            for p in pars:
                kod = p.get("KodBahagianPilihanRaya")
                r = json.loads(post(op, "/semakan/keputusan/keputusanPru",
                                    {"_token": token, "kategori": "PRU",
                                     "PilihanrayaId": pru_id, "kodbahagian": kod,
                                     "DunId": "{FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF}",
                                     "RefNegeriId": state_id},
                                    "/semakan/keputusan/pru"))
                seat = parse_result(r, "pru")
                seat["state"] = state_name.strip()
                seat["name"] = f"P.{kod} {p.get('NamaBahagianPilihanRaya', '')}".strip()
                seats.append(seat)
                time.sleep(POLL)
    except Exception as e:
        sys.stderr.write(f"PRU crawl failed: {e}\n")

    # ── DUN (latest state election for EVERY state) ───────────────────
    try:
        html = get(op, "/semakan/keputusan/pru-dun")
        token = token_of(html)
        # The #PruDun dropdown lists every state election with its state id,
        # newest first per state - take the FIRST option per state. Perlis,
        # Perak and Pahang are absent because their state elections rode
        # PRU-15 (Nov 2022); their DUN seats come from getParDun's dun
        # payload on the PRU page (same keputusanPru endpoint).
        dun_opts = re.findall(r'<option class="font-bold" data-negeri="([A-F0-9-]{36})" value="([A-F0-9-]{36})">([^<]+)</option>', html)
        if not dun_opts:
            raise ValueError("DUN election options not found")
        # state id -> (election id, name) for the newest election of that state
        latest_dun = {}
        for nid, did, dname in dun_opts:
            if nid not in latest_dun:
                latest_dun[nid] = (did, dname)
        sys.stderr.write(f"DUN: {len(latest_dun)} states with dropdown elections\n")
        meta["dun"] = {"name": f"latest state election per state ({len(latest_dun)} dropdown + PRU-embedded)",
                       "states": len(states)}
        for nid, (did, dname) in latest_dun.items():
            state_name = next((s.strip() for s_id, s in states if s_id == nid), nid)
            try:
                d = json.loads(post(op, "/semakan/keputusan/senaraiDunPruDun",
                                    {"_token": token, "PilihanrayaId": did, "RefNegeriId": nid},
                                    "/semakan/keputusan/pru-dun"))
                duns = (d.get("dun") or [])
                if LIMIT and LIMIT > 0:
                    duns = duns[:LIMIT]
            except Exception as e:
                sys.stderr.write(f"DUN {state_name}: senaraiDunPruDun failed: {e}\n")
                continue
            for dun in duns:
                try:
                    r = json.loads(post(op, "/semakan/keputusan/keputusanPruDun",
                                        {"_token": token, "kategori": "PRU_DUN",
                                         "PilihanrayaId": did, "RefNegeriId": nid,
                                         "kodbahagian": dun.get("AppendKod")},
                                        "/semakan/keputusan/pru-dun"))
                    seat = parse_result(r, "dun")
                    seat["state"] = state_name
                    seat["name"] = f"N.{dun.get('KodBahagianPilihanRaya', '')} {dun.get('NamaBahagianPilihanRaya', '')}".strip()
                    seats.append(seat)
                    time.sleep(POLL)
                except Exception as e:
                    sys.stderr.write(f"DUN {state_name} {dun.get('NamaBahagianPilihanRaya')}: {e}\n")
                    fails += 1
                    if fails > MAX_FAILS:
                        raise RuntimeError("too many consecutive DUN failures")
        # PRU-embedded state elections: Perlis, Perak, Pahang rode PRU-15.
        # getParDun carries their DUN seats; the label reads "PRU KE-15", so
        # rename it to a state-election label.
        pru_html = get(op, "/semakan/keputusan/pru")
        pru_token = token_of(pru_html)
        for state_id, state_name in states:
            sn = state_name.strip()
            if state_id in latest_dun or not pru_id:
                continue   # already covered by the dropdown, or no PRU id
            try:
                d = json.loads(post(op, "/semakan/keputusan/pru/getParDun",
                                    {"_token": pru_token, "RefNegeriId": state_id,
                                     "PilihanrayaId": pru_id},
                                    "/semakan/keputusan/pru"))
                dun_payload = d.get("dun")
                duns = []
                if isinstance(dun_payload, dict):
                    inner = dun_payload.get("dun")
                    if isinstance(inner, list):
                        duns = inner
                if not duns:
                    continue   # no state election rode that PRU
                sys.stderr.write(f"DUN {sn}: {len(duns)} seats via PRU-{pru_id[:8]}\n")
                for dun in duns:
                    r = json.loads(post(op, "/semakan/keputusan/keputusanPru",
                                        {"_token": pru_token, "kategori": "PRU",
                                         "PilihanrayaId": pru_id,
                                         "RefNegeriId": state_id,
                                         "kodbahagian": dun.get("AppendKod")},
                                        "/semakan/keputusan/pru"))
                    seat = parse_result(r, "dun")
                    seat["state"] = sn
                    seat["name"] = f"N.{dun.get('KodBahagianPilihanRaya', '')} {dun.get('NamaBahagianPilihanRaya', '')}".strip()
                    seat["election"] = f"PRU DEWAN NEGERI {sn} KE-15 (2022)"
                    seats.append(seat)
                    time.sleep(POLL)
            except Exception as e:
                sys.stderr.write(f"DUN {sn} (PRU-embedded): {e}\n")
    except Exception as e:
        sys.stderr.write(f"DUN crawl failed: {e}\n")

    # ── PRK (latest by-election) ───────────────────────────────────────
    try:
        html = get(op, "/semakan/keputusan/prk")
        token = token_of(html)
        # PRK is a <select> of by-elections, ordered newest-first
        prk_tabs = re.findall(r'<option value="([A-F0-9-]{36})" class="font-bold">([^<]{5,60})</option>', html)
        if not prk_tabs:
            raise ValueError("PRK tabs not found")
        pid, pname = prk_tabs[0][0], prk_tabs[0][1].strip()
        meta["prk"] = {"id": pid, "name": pname}
        r = json.loads(post(op, "/semakan/keputusan/keputusanPrk",
                            {"_token": token, "kategori": "PRK", "PilihanrayaId": pid},
                            "/semakan/keputusan/prk"))
        seat = parse_result(r, "prk")
        seat["name"] = pname
        seats.append(seat)
        sys.stderr.write(f"PRK: {pname}\n")
    except Exception as e:
        sys.stderr.write(f"PRK crawl failed: {e}\n")

    if not seats:
        sys.stderr.write("election: no seats collected - keeping previous file\n")
        return 1

    out = {
        "generated": date.today().isoformat(),
        "source": "Suruhanjaya Pilihan Raya (SPR) MySPRSemak",
        "note": "Latest election per category - results are static once published. "
                "DUN = the latest state election for EVERY state: 10 states come "
                "from the pru-dun dropdown (Negeri Sembilan KE-16, Johor KE-16, "
                "Sabah KE-17, Sarawak KE-12, Melaka KE-15, and 2023 elections in "
                "Kedah/Kelantan/Penang/Selangor/Terengganu); Perlis, Perak and "
                "Pahang held their state elections with PRU-15 and come from its "
                "DUN payload. SPR's getParDun omits Kedah P.017 Padang Serai (2023 "
                "by-election seat), and the 13 federal-territory seats "
                "(KL/Putrajaya/Labuan) have no state entry in SPR's dropdown, so "
                "PRU-15 is 208 seats here vs 222 nationally.",
        "categories": meta,
        "seats": seats,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"), ensure_ascii=False)
    sys.stderr.write(f"election: wrote {OUT} ({len(seats)} seats)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
