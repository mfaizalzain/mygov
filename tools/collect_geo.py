#!/usr/bin/env python3
"""Geography collector: population and socioeconomics below the national level.

The dashboard's Population section only ever showed the national total, because
that is the only level served by the OpenAPI. Everything below it is either
excluded from the API or answers empty:

  population_state      404 on the API; the API's own copy stops at 2023 while
                        the Parquet runs to 2026 - the README's "not updated
                        since 2023" was true of the endpoint, not the data
  population_district   API returns `Valid columns: []`
  population_parlimen   404 - Parquet only
  population_dun        404 - Parquet only

So this collector reads them from storage.dosm.gov.my (note: the *dosm* host,
not storage.data.gov.my, which serves everything else) and writes
public/geo.json.

  Writes: public/geo.json  (uploaded to KV by the GitHub Action)

Two things to know about the constituency tables
------------------------------------------------
1. They advertise "SEX, ETHNICITY, AGE" but carry no real age bands and no
   ethnic groups - `age` and `ethnicity` only ever hold overall/citizen/
   noncitizen. **Voting-age population per seat is not derivable.** Citizen
   population is the closest available proxy for an electorate, and it must be
   labelled as a proxy: it still includes everyone under 18.
2. Citizenship is encoded in the **`age`** column for the multi-year series
   (`age='citizen'`, `ethnicity='overall'`). The `ethnicity='citizen'` rows
   are a single year only, so the obvious filter silently returns nothing.

State and district tables are different - those do carry real age bands and
ethnicities, so they support a composition breakdown and the constituency
tables do not.

There is no election data anywhere on data.gov.my - no results, no candidates,
no voter rolls. This is "know your constituency", not results.

Run:  python3 tools/collect_geo.py
Deps: pandas, pyarrow (Parquet, same as collect_prices.py)
"""
import datetime as dt
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

POP = "https://storage.dosm.gov.my/population/"
API = "https://api.data.gov.my/data-catalogue/"
OUT = "public/geo.json"

TREND_FROM = 1970          # state series runs to 1970; district only to 2020
MIN_SEATS = 100            # sanity floor before we agree to publish


def fetch(url, tries=4):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read()
        except Exception as e:
            last = e
            sys.stderr.write(f"  attempt {attempt + 1}/{tries} failed {url[-46:]}: {e}\n")
            if attempt < tries - 1:
                time.sleep(5 * (attempt + 1))
    raise last or RuntimeError(url)


def parquet(name):
    sys.stderr.write(f"  {name}\n")
    return pd.read_parquet(io.BytesIO(fetch(POP + name + ".parquet")))


def api(dataset, **params):
    """One data-catalogue call. Spaced by the caller - the limiter is 4/min
    per family and every one of these is the same family."""
    params["id"] = dataset
    qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    raw = fetch(API + "?" + qs)
    return json.loads(raw.decode("utf-8"))


def num(v, nd=1):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else round(f, nd)


def year_of(s):
    return int(str(s)[:4])


def overall(df):
    """The plain total row: both sexes, all ages, all ethnicities."""
    return df[(df.sex == "both") & (df.age == "overall") & (df.ethnicity == "overall")]


def build_state(df):
    df = df.copy()
    df["y"] = df.date.astype(str).str[:4].astype(int)
    ov = overall(df)
    # int() matters: pandas hands back numpy int64, which json.dump refuses.
    years = sorted(int(y) for y in ov.y.unique() if y >= TREND_FROM)
    trend = {}
    for state, g in ov.groupby("state"):
        m = dict(zip(g.y, g.population))
        trend[state] = [num(m.get(y)) for y in years]
    latest = int(max(years))

    cur = df[df.y == latest]
    # Real ethnic groups exist at this level (unlike the constituency tables).
    eth, ages = {}, {}
    for state, g in cur[(cur.sex == "both") & (cur.age == "overall")].groupby("state"):
        eth[state] = {r.ethnicity: num(r.population)
                      for r in g.itertuples() if r.ethnicity != "overall"}
    for state, g in cur[(cur.sex == "both") & (cur.ethnicity == "overall")].groupby("state"):
        ages[state] = {r.age: num(r.population)
                       for r in g.itertuples() if r.age != "overall"}
    sex = {}
    for state, g in cur[(cur.age == "overall") & (cur.ethnicity == "overall")].groupby("state"):
        d = {r.sex: num(r.population) for r in g.itertuples()}
        sex[state] = [d.get("male"), d.get("female")]
    return {"years": years, "trend": trend, "latest": latest,
            "eth": eth, "age": ages, "sex": sex}


def district_eth_sx(cur):
    """Pure: per-district ethnicity + sex split from the newest-year slice.

    cur : DataFrame (or anything itertuples-able) with columns
          state, district, sex, age, ethnicity, population, restricted to the
          latest year. Mirrors build_state's composition extraction, but
          keyed by (state, district) instead of state.
    Returns {state|district: {"eth": {group: pop}, "sx": {"male": pop, "female": pop}}}
    for the districts present in `cur`. Values are rounded to 1 decimal
    (thousands, as published)."""
    out = {}
    eth = {}
    for st, g in cur[(cur.sex == "both") & (cur.age == "overall")].groupby(["state", "district"]):
        eth[st] = {r.ethnicity: num(r.population)
                   for r in g.itertuples() if r.ethnicity != "overall"}
    sx = {}
    for st, g in cur[(cur.age == "overall") & (cur.ethnicity == "overall")].groupby(["state", "district"]):
        d = {r.sex: num(r.population) for r in g.itertuples()}
        sx[st] = {"male": d.get("male"), "female": d.get("female")}
    for key in set(eth) | set(sx):
        e, s = eth.get(key), sx.get(key)
        row = {}
        if e:
            row["eth"] = e
        if s and (s["male"] is not None or s["female"] is not None):
            row["sx"] = s
        if row:
            out[key] = row
    return out


def district_age(cur):
    """Pure: per-district age structure as three broad shares (%). Age is a
    socio signal - a youth-heavy district faces schooling/entertainment
    demand, a work-heavy one commutes and taxes, an old one needs health
    and accessibility - so three numbers carry the signal that eighteen
    bands would drown in. Returns {state|district: {"young": %, "work": %,
    "old": %}} for districts present in `cur`."""
    def band_of(a):
        a = str(a)
        if a == "85+":
            return "old"
        n = int(a.split("-")[0])
        return "young" if n < 15 else ("work" if n < 65 else "old")

    out = {}
    rows = cur[(cur.sex == "both") & (cur.ethnicity == "overall") & (cur.age != "overall")]
    for (st, d), g in rows.groupby(["state", "district"]):
        tot = float(g.population.sum())
        if not tot:
            continue
        m = {"young": 0.0, "work": 0.0, "old": 0.0}
        for r in g.itertuples():
            m[band_of(r.age)] += float(r.population)
        out[(st, d)] = {k: round(v / tot * 100, 1) for k, v in m.items()}
    return out


def build_district(df):
    df = df.copy()
    df["y"] = df.date.astype(str).str[:4].astype(int)
    ov = overall(df)
    latest = int(ov.y.max())
    cur = ov[ov.y == latest]
    prev = ov[ov.y == ov[ov.y < latest].y.max()] if (ov.y < latest).any() else None
    pm = {} if prev is None else dict(zip(prev.district, prev.population))
    # Composition comes from the full latest-year slice (not the overall rows):
    # ethnicity and sex live in the dimension rows, so they need the
    # unrestricted dataframe at the same year as the totals.
    full = df[df.y == latest]
    comp = district_eth_sx(full)
    age = district_age(full)
    rows = []
    for r in cur.itertuples():
        was = pm.get(r.district)
        row = {"n": r.district, "s": r.state, "p": num(r.population),
               "g": None if not was else num((r.population / was - 1) * 100, 2)}
        row.update(comp.get((r.state, r.district), {}))
        a = age.get((r.state, r.district))
        if a:
            row["age"] = a
        rows.append(row)
    rows.sort(key=lambda x: -(x["p"] or 0))
    # 4 of the 164 districts carry no row for the newest year upstream. Ship
    # both counts so the UI can say so instead of quietly showing 160.
    return {"year": latest, "list": rows,
            "known": int(ov.district.nunique())}


def build_seats(df, level):
    """parlimen or dun. Citizenship lives in the `age` column here - see the
    module docstring. Seat labels arrive as 'P.102 Bangi'; the code is split
    out so the UI can sort and search on either half."""
    df = df.copy()
    df["y"] = df.date.astype(str).str[:4].astype(int)
    latest = int(df.y.max())
    cur = df[df.y == latest]

    tot = cur[(cur.sex == "both") & (cur.age == "overall") & (cur.ethnicity == "overall")]
    cit = cur[(cur.sex == "both") & (cur.age == "citizen") & (cur.ethnicity == "overall")]
    cmap = dict(zip(cit[level], cit.population))

    rows = []
    for r in tot.itertuples():
        label = str(getattr(r, level)).strip()
        code, _, name = label.partition(" ")
        # `k` is the socio join key - the full label; see code_of() above.
        item = {"k": label, "c": code, "n": name or label, "s": r.state,
                "p": num(r.population), "cz": num(cmap.get(label))}
        if level == "dun":
            pl = str(r.parlimen)
            item["pc"] = pl.split(" ")[0]
        rows.append(item)
    rows.sort(key=lambda x: x["c"])
    return {"year": latest, "list": rows}


def build_socio(level):
    """Income, poverty, inequality and labour force per seat. Unlike the
    population tables these ARE on the OpenAPI, so they come over the API."""
    out = {}

    def put(code, key, val):
        if val is not None:
            out.setdefault(code, {})[key] = val

    def code_of(row):
        """The join key is the FULL seat label, not the code.
        DUN numbers restart in every state - N.01 exists sixteen times - so
        keying on the bare code silently collapsed 600 seats into 82 and left
        most of the country without socioeconomics. Parliament codes happen to
        be globally unique, but both levels use the same scheme so the UI does
        not have to care. Both sources emit the label identically."""
        return str(row.get(level, "")).strip()

    jobs = [
        (f"hh_income_{level}",     lambda r: [("inc", num(r.get("income_median"), 0))]),
        (f"hh_poverty_{level}",    lambda r: [("pov", num(r.get("poverty_absolute"), 2))]),
        (f"hh_inequality_{level}", lambda r: [("gini", num(r.get("gini"), 3))]),
        (f"lfs_{level}",           lambda r: [("u", num(r.get("u_rate"), 1)),
                                              ("pr", num(r.get("p_rate"), 1))]),
    ]
    for i, (ds, pick) in enumerate(jobs):
        if i:
            time.sleep(16)   # 4 requests/min per family; stay well under
        try:
            rows = api(ds, sort="-date")
        except Exception as e:
            sys.stderr.write(f"  {ds}: {e} - skipped\n")
            continue
        if not rows:
            continue
        newest = max(str(r.get("date", "")) for r in rows)
        n = 0
        for r in rows:
            if str(r.get("date", "")) != newest:
                continue
            c = code_of(r)
            if not c:
                continue
            for k, v in pick(r):
                put(c, k, v)
            n += 1
        sys.stderr.write(f"  {ds}: {n} seats @ {newest[:4]}\n")
    return out


def build_district_socio(district_rows):
    """Income, poverty and inequality per DISTRICT (OpenAPI). Unlike the
    constituency socio which keys on seat labels, district datasets carry
    state + district columns - join on the pair. Returns {state|district:
    {"inc": median_rm, "pov": abs_pct, "gini": 0-1}} for the newest release
    year only (2019/2022/2024 - DOSM publishes these in waves)."""
    jobs = [
        ("hh_income_district",     lambda r: [("inc", num(r.get("income_median"), 0))]),
        ("hh_poverty_district",    lambda r: [("pov", num(r.get("poverty_absolute"), 2))]),
        ("hh_inequality_district", lambda r: [("gini", num(r.get("gini"), 3))]),
    ]
    # (state, district) keys as they appear in the population table.
    want = {(r["s"], r["n"]) for r in district_rows}
    out = {}
    for i, (ds, pick) in enumerate(jobs):
        if i:
            time.sleep(16)   # same 4-requests/min family as build_socio
        try:
            rows = api(ds, sort="-date")
        except Exception as e:
            sys.stderr.write(f"  {ds}: {e} - skipped\n")
            continue
        if not rows:
            continue
        newest = max(str(r.get("date", "")) for r in rows)
        n = 0
        for r in rows:
            if str(r.get("date", "")) != newest:
                continue
            key = (str(r.get("state", "")).strip(), str(r.get("district", "")).strip())
            if key not in want:
                continue
            for k, v in pick(r):
                if v is not None:
                    out.setdefault(key, {})[k] = v
            n += 1
        sys.stderr.write(f"  {ds}: {n} districts @ {newest[:4]}\n")
    return out


def main():
    sys.stderr.write("fetching population parquet\n")
    state = build_state(parquet("population_state"))
    district = build_district(parquet("population_district"))
    parlimen = build_seats(parquet("population_parlimen"), "parlimen")
    dun = build_seats(parquet("population_dun"), "dun")

    sys.stderr.write("fetching constituency socioeconomics (OpenAPI)\n")
    socio_p = build_socio("parlimen")
    time.sleep(16)
    socio_d = build_socio("dun")

    # District-level income/poverty/gini - the district table gains these
    # columns in the same shape as the constituency socio (inc/pov/gini).
    time.sleep(16)
    dist_socio = build_district_socio(district["list"])
    for row in district["list"]:
        row.update(dist_socio.get((row["s"], row["n"]), {}))

    if len(parlimen["list"]) < MIN_SEATS or len(district["list"]) < MIN_SEATS:
        raise SystemExit("geo: too few seats/districts, refusing to write")

    payload = {
        "generated": dt.date.today().isoformat(),
        "note": ("population_* below national level is Parquet-only; the "
                 "constituency tables carry no age bands, so citizen count is "
                 "a proxy for electorate, not a voting-age population"),
        "state": state,
        "district": district,
        "parlimen": parlimen,
        "dun": dun,
        "socio": {"parlimen": socio_p, "dun": socio_d},
    }
    with open(OUT, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    sizes = {k: len(json.dumps(v, separators=(",", ":")))
             for k, v in payload.items() if k not in ("generated", "note")}
    sys.stderr.write(f"wrote {OUT} ({len(open(OUT).read()):,} bytes): "
                     + ", ".join(f"{k}={v:,}" for k, v in sizes.items()) + "\n")


if __name__ == "__main__":
    main()
