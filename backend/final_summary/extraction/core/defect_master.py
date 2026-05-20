"""
defect_master.py
----------------
Static Python mirror of defect_master.sql.

Structure per template
----------------------
  DEFECT_MASTER[template_key] = {
      "categories": {
          "code": {"label": str, "sort_order": int}
      },
      "items": [
          {
              "item_no":       int,          # sequential position in the Excel
              "category_code": str,          # maps to categories above
              "name":          str,          # canonical name saved to DB
              "sort_order":    int,
          },
          ...
      ]
  }

Template keys align with ReportType / defect_column_count in BuyerFactoryPair:
  "TEMPLATE_31"  →  31 items  (KNIT_35 maps here — 31 actual defect items)
  "TEMPLATE_37"  →  37 items  (WOVEN_37, SWEATER_37)
  "TEMPLATE_78"  →  78 items  (WOVEN_78)

HOW TO EDIT
-----------
- To rename a defect item: change "name" only. item_no / sort_order must stay stable.
- To add a new template: copy the pattern, add an entry to TEMPLATE_FOR_COUNT.
- To change category labels: edit "label" in the categories dict.

TEMPLATE_FOR_COUNT
------------------
Maps defect_column_count (from BuyerFactoryPair.defect_column_count) to a
template key. Tolerance of ±4 is applied by the extractor.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

DEFECT_MASTER: dict[str, dict] = {}


# =============================================================================
# TEMPLATE_31  (31 items — PQC / Japanese layout, KNIT-type)
# =============================================================================

DEFECT_MASTER["TEMPLATE_31"] = {
    "categories": {
        "A": {"label": "SPEC",                   "sort_order": 1},
        "B": {"label": "LOOKING FOR FINISH GOOD", "sort_order": 2},
        "C": {"label": "FABRIC",                  "sort_order": 3},
        "D": {"label": "SEWING PROCESS",          "sort_order": 4},
        "E": {"label": "ACCESSORY",               "sort_order": 5},
        "F": {"label": "OTHER",                   "sort_order": 6},
    },
    "items": [
        # ── A : SPEC ──────────────────────────────────────────────────────
        {"item_no": 1,  "category_code": "A", "name": "Size Mix サイズ間違い",              "sort_order": 1},
        {"item_no": 2,  "category_code": "A", "name": "Size Label Wrong ラベル間違い",      "sort_order": 2},
        {"item_no": 3,  "category_code": "A", "name": "Measurement Problem 寸法不良",       "sort_order": 3},
        # ── B : LOOKING FOR FINISH GOOD ───────────────────────────────────
        {"item_no": 4,  "category_code": "B", "name": "Bad Looking 形状不良、不対象、段差", "sort_order": 4},
        {"item_no": 5,  "category_code": "B", "name": "Shading Problem 仕上げアイロン不良", "sort_order": 5},
        {"item_no": 6,  "category_code": "B", "name": "Ironing Problem アタリ、しわ",       "sort_order": 6},
        {"item_no": 7,  "category_code": "B", "name": "Twist ねじれ",                       "sort_order": 7},
        {"item_no": 8,  "category_code": "B", "name": "Oil Dirty 油汚れ",                   "sort_order": 8},
        {"item_no": 9,  "category_code": "B", "name": "Other Dirty 汚れ、しみ",             "sort_order": 9},
        # ── C : FABRIC ────────────────────────────────────────────────────
        {"item_no": 10, "category_code": "C", "name": "Em+Prt. Problem 刺繍、プリント不良", "sort_order": 10},
        {"item_no": 11, "category_code": "C", "name": "Weaving/Knitting Defect 織りキズ、ムラ", "sort_order": 11},
        {"item_no": 12, "category_code": "C", "name": "Hole or Broken Fabric 穴、傷、破れ","sort_order": 12},
        {"item_no": 13, "category_code": "C", "name": "Dust/Loosed Thread Insert 縫い目笑い", "sort_order": 13},
        {"item_no": 14, "category_code": "C", "name": "Crease Marks リードマーク",          "sort_order": 14},
        {"item_no": 15, "category_code": "C", "name": "Dyeing problem 染色むら",            "sort_order": 15},
        {"item_no": 16, "category_code": "C", "name": "Strengtheners in Fabric 伸度不足",   "sort_order": 16},
        # ── D : SEWING PROCESS ────────────────────────────────────────────
        {"item_no": 17, "category_code": "D", "name": "Thread is Broken 縫い糸切れ",        "sort_order": 17},
        {"item_no": 18, "category_code": "D", "name": "Seam Defect 縫いはずれ",             "sort_order": 18},
        {"item_no": 19, "category_code": "D", "name": "Missing Stitch 縫い忘れ",            "sort_order": 19},
        {"item_no": 20, "category_code": "D", "name": "Drop Stitch 縫い落ち",               "sort_order": 20},
        {"item_no": 21, "category_code": "D", "name": "Skip Stitch 目飛び",                 "sort_order": 21},
        {"item_no": 22, "category_code": "D", "name": "Needle Hole 針落ち痕",               "sort_order": 22},
        {"item_no": 23, "category_code": "D", "name": "Thread tension loosed 糸調子不良",   "sort_order": 23},
        {"item_no": 24, "category_code": "D", "name": "Bad Sewing 縫製不良",                "sort_order": 24},
        # ── E : ACCESSORY ─────────────────────────────────────────────────
        {"item_no": 25, "category_code": "E", "name": "Accessory Wrong Attach 付け位置違い","sort_order": 25},
        {"item_no": 26, "category_code": "E", "name": "Accessory Mistake 取付け不良",        "sort_order": 26},
        {"item_no": 27, "category_code": "E", "name": "Accessory Damaging 材質不良",         "sort_order": 27},
        {"item_no": 28, "category_code": "E", "name": "Accessory Missing 付け忘れ，脱落",    "sort_order": 28},
        # ── F : OTHER ─────────────────────────────────────────────────────
        {"item_no": 29, "category_code": "F", "name": "Uncut Thread 糸始末不良",            "sort_order": 29},
        {"item_no": 30, "category_code": "F", "name": "QC Sticker Appear シール取り忘れ",   "sort_order": 30},
        {"item_no": 31, "category_code": "F", "name": "Others その他",                      "sort_order": 31},
    ],
}


# =============================================================================
# TEMPLATE_37  (37 items — Standard / SPI layout, WOVEN / SWEATER)
# =============================================================================

DEFECT_MASTER["TEMPLATE_37"] = {
    "categories": {
        "A": {"label": "素材不良 Material Defects", "sort_order": 1},
        "B": {"label": "縫製不良 Sewing Defects",   "sort_order": 2},
        "C": {"label": "付属不良 Trim Defects",     "sort_order": 3},
        "D": {"label": "仕上げ不良 Finishing Defects", "sort_order": 4},
        "E": {"label": "他 Others",                 "sort_order": 5},
    },
    "items": [
        # ── A : Material Defects ──────────────────────────────────────────
        {"item_no": 1,  "category_code": "A", "name": "Nep, slub, fly",                                        "sort_order": 1},
        {"item_no": 2,  "category_code": "A", "name": "Holes, scratches, tears",                               "sort_order": 2},
        {"item_no": 3,  "category_code": "A", "name": "Uneven Dyeing, Color shading, warp/weft streak",        "sort_order": 3},
        {"item_no": 4,  "category_code": "A", "name": "Poor Texture, Bad handfeel, Bad surface",               "sort_order": 4},
        {"item_no": 5,  "category_code": "A", "name": "Skew",                                                  "sort_order": 5},
        {"item_no": 6,  "category_code": "A", "name": "Bad smell/ Odor",                                       "sort_order": 6},
        {"item_no": 7,  "category_code": "A", "name": "Other",                                                 "sort_order": 7},
        # ── B : Sewing Defects ────────────────────────────────────────────
        {"item_no": 8,  "category_code": "B", "name": "Poor Shape (Bad form), non-symmetrical, dislocation",   "sort_order": 8},
        {"item_no": 9,  "category_code": "B", "name": "Poor Joining of pattern/ Poor print/embroidery",        "sort_order": 9},
        {"item_no": 10, "category_code": "B", "name": "Staggered seams, spirality, wrinkles",                  "sort_order": 10},
        {"item_no": 11, "category_code": "B", "name": "Puckering, gathered stitching",                         "sort_order": 11},
        {"item_no": 12, "category_code": "B", "name": "Broken Stitches/ Broken Seam",                          "sort_order": 12},
        {"item_no": 13, "category_code": "B", "name": "Broken Material (From Stitching)",                      "sort_order": 13},
        {"item_no": 14, "category_code": "B", "name": "Insufficient stretch in seams",                         "sort_order": 14},
        {"item_no": 15, "category_code": "B", "name": "Poor stitch length, poor thread tension",               "sort_order": 15},
        {"item_no": 16, "category_code": "B", "name": "Insufficient seam allowance, run-off stitches",         "sort_order": 16},
        {"item_no": 17, "category_code": "B", "name": "Needle marks, restitched seams",                        "sort_order": 17},
        {"item_no": 18, "category_code": "B", "name": "Exposed lining",                                        "sort_order": 18},
        {"item_no": 19, "category_code": "B", "name": "Skipped stitches",                                      "sort_order": 19},
        {"item_no": 20, "category_code": "B", "name": "Sewn by mistake, puckered seams, pleated",              "sort_order": 20},
        {"item_no": 21, "category_code": "B", "name": "Missing stitches, missing bartacks",                    "sort_order": 21},
        {"item_no": 22, "category_code": "B", "name": "Insufficient strength / Bad reinforce stitch",          "sort_order": 22},
        {"item_no": 23, "category_code": "B", "name": "Other",                                                 "sort_order": 23},
        # ── C : Trim Defects ──────────────────────────────────────────────
        {"item_no": 24, "category_code": "C", "name": "Poor Quality (faded, burred, rusty, dirty)",            "sort_order": 24},
        {"item_no": 25, "category_code": "C", "name": "Poorly attached trim (deformed, damaged)",              "sort_order": 25},
        {"item_no": 26, "category_code": "C", "name": "Missing Trim (detached)",                               "sort_order": 26},
        {"item_no": 27, "category_code": "C", "name": "Misplaced/ incorrect trim",                             "sort_order": 27},
        {"item_no": 28, "category_code": "C", "name": "Poorly functioning",                                    "sort_order": 28},
        # ── D : Finishing Defects ─────────────────────────────────────────
        {"item_no": 29, "category_code": "D", "name": "Bad thread trimming, lint (thread end left)",           "sort_order": 29},
        {"item_no": 30, "category_code": "D", "name": "Dirty, Stains",                                         "sort_order": 30},
        {"item_no": 31, "category_code": "D", "name": "Poor shape, Bad form, non-symmetrical",                 "sort_order": 31},
        {"item_no": 32, "category_code": "D", "name": "Shining mark, wrinkles",                                "sort_order": 32},
        {"item_no": 33, "category_code": "D", "name": "Poor wash Treatment",                                   "sort_order": 33},
        {"item_no": 34, "category_code": "D", "name": "Poor Measurement / wrong Measurement",                  "sort_order": 34},
        # ── E : Others ────────────────────────────────────────────────────
        {"item_no": 35, "category_code": "E", "name": "Poor Packaging",                                        "sort_order": 35},
        {"item_no": 36, "category_code": "E", "name": "Wrong quantity Packed",                                  "sort_order": 36},
        {"item_no": 37, "category_code": "E", "name": "Other",                                                 "sort_order": 37},
    ],
}


# =============================================================================
# TEMPLATE_78  (78 items — SPI / Woven-78)
# =============================================================================

DEFECT_MASTER["TEMPLATE_78"] = {
    "categories": {
        "A": {"label": "Fabrics", "sort_order": 1},
        "B": {"label": "Sewing",  "sort_order": 2},
        "C": {"label": "ACC",     "sort_order": 3},
        "D": {"label": "Finish",  "sort_order": 4},
        "E": {"label": "Safety",  "sort_order": 5},
        "F": {"label": "Others",  "sort_order": 6},
    },
    "items": [
        # ── A : Fabrics ───────────────────────────────────────────────────
        {"item_no": 1,  "category_code": "A", "name": "Damage",                              "sort_order": 1},
        {"item_no": 2,  "category_code": "A", "name": "Needle breakage defect",              "sort_order": 2},
        {"item_no": 3,  "category_code": "A", "name": "Hole, tear",                          "sort_order": 3},
        {"item_no": 4,  "category_code": "A", "name": "NEP",                                 "sort_order": 4},
        {"item_no": 5,  "category_code": "A", "name": "SLUB",                                "sort_order": 5},
        {"item_no": 6,  "category_code": "A", "name": "Weft defect",                         "sort_order": 6},
        {"item_no": 7,  "category_code": "A", "name": "Unexpected things interwoven",        "sort_order": 7},
        {"item_no": 8,  "category_code": "A", "name": "Bowing",                              "sort_order": 8},
        {"item_no": 9,  "category_code": "A", "name": "Odor",                                "sort_order": 9},
        {"item_no": 10, "category_code": "A", "name": "Uneven dyeing",                       "sort_order": 10},
        {"item_no": 11, "category_code": "A", "name": "Texture, surface defect",             "sort_order": 11},
        {"item_no": 12, "category_code": "A", "name": "Warp and weft defect",                "sort_order": 12},
        # ── B : Sewing ────────────────────────────────────────────────────
        {"item_no": 13, "category_code": "B", "name": "Hue difference",                      "sort_order": 13},
        {"item_no": 14, "category_code": "B", "name": "Unevenness",                          "sort_order": 14},
        {"item_no": 15, "category_code": "B", "name": "Pieces not symmetrical",              "sort_order": 15},
        {"item_no": 16, "category_code": "B", "name": "Deformation (Defect in shape)",       "sort_order": 16},
        {"item_no": 17, "category_code": "B", "name": "Tight or loose part of fabric",       "sort_order": 17},
        {"item_no": 18, "category_code": "B", "name": "Uneven seam",                         "sort_order": 18},
        {"item_no": 19, "category_code": "B", "name": "Spiralty, wrinkle",                   "sort_order": 19},
        {"item_no": 20, "category_code": "B", "name": "PUCKERING",                           "sort_order": 20},
        {"item_no": 21, "category_code": "B", "name": "Corrugation",                         "sort_order": 21},
        {"item_no": 22, "category_code": "B", "name": "Thread breakage",                     "sort_order": 22},
        {"item_no": 23, "category_code": "B", "name": "Lack of elasticity",                  "sort_order": 23},
        {"item_no": 24, "category_code": "B", "name": "Incorrect stitching number",          "sort_order": 24},
        {"item_no": 25, "category_code": "B", "name": "Stitches out of seam allowance",      "sort_order": 25},
        {"item_no": 26, "category_code": "B", "name": "Missing stitch",                      "sort_order": 26},
        {"item_no": 27, "category_code": "B", "name": "Lack of seam allowance",              "sort_order": 27},
        {"item_no": 28, "category_code": "B", "name": "Unexpected tuck",                     "sort_order": 28},
        {"item_no": 29, "category_code": "B", "name": "Unexpected fullness",                 "sort_order": 29},
        {"item_no": 30, "category_code": "B", "name": "Needle mark",                         "sort_order": 30},
        {"item_no": 31, "category_code": "B", "name": "Sewing defects caused by machine",    "sort_order": 31},
        {"item_no": 32, "category_code": "B", "name": "Incorrect size of lining",            "sort_order": 32},
        {"item_no": 33, "category_code": "B", "name": "Skipped stitch",                      "sort_order": 33},
        {"item_no": 34, "category_code": "B", "name": "Sewing involving unexpected parts",   "sort_order": 34},
        {"item_no": 35, "category_code": "B", "name": "Missing sewing process",              "sort_order": 35},
        {"item_no": 36, "category_code": "B", "name": "Mislocated bar-tack",                 "sort_order": 36},
        {"item_no": 37, "category_code": "B", "name": "Incorrect thread tension",            "sort_order": 37},
        {"item_no": 38, "category_code": "B", "name": "Falling off of a thread",             "sort_order": 38},
        {"item_no": 39, "category_code": "B", "name": "Lack of reverse stitch",              "sort_order": 39},
        {"item_no": 40, "category_code": "B", "name": "Incorrect easing",                    "sort_order": 40},
        {"item_no": 41, "category_code": "B", "name": "Piecing defect",                      "sort_order": 41},
        {"item_no": 42, "category_code": "B", "name": "Incorrect lapped seam",               "sort_order": 42},
        {"item_no": 43, "category_code": "B", "name": "Incorrect trimming",                  "sort_order": 43},
        {"item_no": 44, "category_code": "B", "name": "Lack of strength",                    "sort_order": 44},
        {"item_no": 45, "category_code": "B", "name": "Incorrect buttonhole sewing",         "sort_order": 45},
        {"item_no": 46, "category_code": "B", "name": "Incorrect brand label sewing",        "sort_order": 46},
        {"item_no": 47, "category_code": "B", "name": "Sewing slip",                         "sort_order": 47},
        {"item_no": 48, "category_code": "B", "name": "Incorrect position",                  "sort_order": 48},
        {"item_no": 49, "category_code": "B", "name": "Incorrect pattern matching",          "sort_order": 49},
        {"item_no": 50, "category_code": "B", "name": "Peel off glue/delamination",          "sort_order": 50},
        {"item_no": 51, "category_code": "B", "name": "Visible/see through glue",            "sort_order": 51},
        {"item_no": 52, "category_code": "B", "name": "Bonding seam uneven/wavy",            "sort_order": 52},
        {"item_no": 53, "category_code": "B", "name": "Bonding seam not catch up/bad selvaged", "sort_order": 53},
        {"item_no": 54, "category_code": "B", "name": "Stick glue/leaking glue",             "sort_order": 54},
        {"item_no": 55, "category_code": "B", "name": "Mold Shape",                          "sort_order": 55},
        {"item_no": 56, "category_code": "B", "name": "Poor application glue position",      "sort_order": 56},
        {"item_no": 57, "category_code": "B", "name": "Yarn severance",                      "sort_order": 57},
        # ── C : ACC ───────────────────────────────────────────────────────
        {"item_no": 58, "category_code": "C", "name": "Unsecured rivet and snap buttons",    "sort_order": 58},
        {"item_no": 59, "category_code": "C", "name": "Incorrect swaging",                   "sort_order": 59},
        {"item_no": 60, "category_code": "C", "name": "Falling off of buttons",              "sort_order": 60},
        {"item_no": 61, "category_code": "C", "name": "Burr",                                "sort_order": 61},
        {"item_no": 62, "category_code": "C", "name": "Incorrect zippers",                   "sort_order": 62},
        {"item_no": 63, "category_code": "C", "name": "Incorrect indication of sub materials","sort_order": 63},
        {"item_no": 64, "category_code": "C", "name": "Incorrect quality of materials",      "sort_order": 64},
        {"item_no": 65, "category_code": "C", "name": "Missing accessories",                 "sort_order": 65},
        {"item_no": 66, "category_code": "C", "name": "Adhesive interlining",                "sort_order": 66},
        # ── D : Finish ────────────────────────────────────────────────────
        {"item_no": 67, "category_code": "D", "name": "Dust, lint",                          "sort_order": 67},
        {"item_no": 68, "category_code": "D", "name": "Smear, stain",                        "sort_order": 68},
        {"item_no": 69, "category_code": "D", "name": "Size",                                "sort_order": 69},
        {"item_no": 70, "category_code": "D", "name": "Peel off and misalignment of prints", "sort_order": 70},
        {"item_no": 71, "category_code": "D", "name": "Pressure mark",                       "sort_order": 71},
        {"item_no": 72, "category_code": "D", "name": "Wash finish",                         "sort_order": 72},
        # ── E : Safety ────────────────────────────────────────────────────
        {"item_no": 73, "category_code": "E", "name": "Thread",                              "sort_order": 73},
        {"item_no": 74, "category_code": "E", "name": "Hazardous object/ foreign bodies",    "sort_order": 74},
        {"item_no": 75, "category_code": "E", "name": "Odor",                                "sort_order": 75},
        # ── F : Others ────────────────────────────────────────────────────
        {"item_no": 76, "category_code": "F", "name": "Bad packing",                         "sort_order": 76},
        {"item_no": 77, "category_code": "F", "name": "Wrong quantity packed",               "sort_order": 77},
        {"item_no": 78, "category_code": "F", "name": "Others",                              "sort_order": 78},
    ],
}


# =============================================================================
# Template selection helpers
# =============================================================================

# Maps defect_column_count → template key.
# The extractor applies ±TOLERANCE when matching.
TEMPLATE_FOR_COUNT: dict[int, str] = {
    31: "TEMPLATE_31",
    37: "TEMPLATE_37",
    78: "TEMPLATE_78",
}

_TOLERANCE = 4


def get_template_key(defect_column_count: int) -> str | None:
    """
    Return the template key for a given defect_column_count.
    Applies ±_TOLERANCE so minor count discrepancies still match.

    Returns None if no template is within tolerance.
    """
    for count, key in TEMPLATE_FOR_COUNT.items():
        if abs(defect_column_count - count) <= _TOLERANCE:
            return key
    return None


def get_items(template_key: str) -> list[dict]:
    """Return the ordered item list for a template (empty list if unknown)."""
    return DEFECT_MASTER.get(template_key, {}).get("items", [])


def get_categories(template_key: str) -> dict[str, dict]:
    """Return the categories dict for a template (empty dict if unknown)."""
    return DEFECT_MASTER.get(template_key, {}).get("categories", {})