-- =============================================================================
-- defect_master.sql
-- =============================================================================
-- Static defect definitions for the three Excel templates used in production.
--
-- HOW TO USE
-- ----------
-- 1. Fill in the INSERT statements below with your actual defect item names.
-- 2. The names MUST match exactly what appears in your Excel defect tables
--    (the extractor matches by name, case-insensitive).
-- 3. Run this file against your audit.db once:
--      sqlite3 C:\AuditSystem\audit.db < defect_master.sql
-- 4. After that the extractor will auto-match each file to the right template.
--
-- TEMPLATE MATCHING
-- -----------------
-- The extractor counts how many defect columns it extracts from each Excel
-- file and picks the nearest template (tolerance ±4):
--   31 items  →  TEMPLATE_31
--   37 items  →  TEMPLATE_37
--   78 items  →  TEMPLATE_78
-- If no template matches, defect_template_id is left NULL (items still saved).
--
-- CATEGORY CODES
-- --------------
--   A = Fabrics / Materials
--   B = Sewing
--   C = Accessories / Trims
--   D = Finishing / Packing
--   E = Safety / Compliance
--   F = Others
-- =============================================================================

-- Re-runnable (INSERT OR IGNORE so safe to run multiple times)

-- ---------------------------------------------------------------------------
-- Templates
-- ---------------------------------------------------------------------------

INSERT OR IGNORE INTO defect_templates (name, item_count) VALUES ('TEMPLATE_31', 31);
INSERT OR IGNORE INTO defect_templates (name, item_count) VALUES ('TEMPLATE_37', 37);
INSERT OR IGNORE INTO defect_templates (name, item_count) VALUES ('TEMPLATE_78', 78);


-- =============================================================================
-- TEMPLATE_31  (31 items)
-- =============================================================================

-- ── Categories ────────────────────────────────────────────────────────────────
INSERT OR IGNORE INTO defect_categories (template_id, code, label, sort_order)
SELECT t31.id, cats.code, cats.label, cats.sort_order
FROM (SELECT id FROM defect_templates WHERE name = 'TEMPLATE_31') t31
CROSS JOIN (
    SELECT 'A' AS code, 'SPEC' AS label, 1 AS sort_order
    UNION ALL SELECT 'B', 'LOOKING FOR FINISH GOOD', 2
    UNION ALL SELECT 'C', 'FABRIC', 3
    UNION ALL SELECT 'D', 'SEWING PROCESS', 4
    UNION ALL SELECT 'E', 'ACCESSORY', 5
    UNION ALL SELECT 'F', 'OTHER', 6
) AS cats;

-- ── Items ─────────────────────────────────────────────────────────────────────
INSERT OR IGNORE INTO defect_items_def (category_id, item_no, name, sort_order)
SELECT dc.id, items.item_no, items.name, items.sort_order
FROM defect_categories dc
JOIN defect_templates dt ON dc.template_id = dt.id
CROSS JOIN (
    -- A : SPEC
    SELECT 'A' AS category_code, 1 AS item_no, 'Size Mix サイズ間違い' AS name, 1 AS sort_order
    UNION ALL SELECT 'A', 2, 'Size Label Wrong ラベル間違い', 2
    UNION ALL SELECT 'A', 3, 'Measurement Problem 寸法不良', 3
    -- B : LOOKING FOR FINISH GOOD
    UNION ALL SELECT 'B', 4, 'Bad Looking 形状不良、不対象、段差', 4
    UNION ALL SELECT 'B', 5, 'Shading Problem 仕上げアイロン不良', 5
    UNION ALL SELECT 'B', 6, 'Ironing Problem アタリ、しわ', 6
    UNION ALL SELECT 'B', 7, 'Twist ねじれ', 7
    UNION ALL SELECT 'B', 8, 'Oil Dirty 油汚れ', 8
    UNION ALL SELECT 'B', 9, 'Other Dirty 汚れ、しみ', 9
    -- C : FABRIC
    UNION ALL SELECT 'C', 10, 'Em+Prt. Problem 刺繍、プリント不良', 10
    UNION ALL SELECT 'C', 11, 'Weaving/Knitting Defect 織りキズ、ムラ', 11
    UNION ALL SELECT 'C', 12, 'Hole or Broken Fabric 穴、傷、破れ', 12
    UNION ALL SELECT 'C', 13, 'Dust/Loosed Thread Insert 縫い目笑い', 13
    UNION ALL SELECT 'C', 14, 'Crease Marks リードマーク', 14
    UNION ALL SELECT 'C', 15, 'Dyeing problem 染色むら', 15
    UNION ALL SELECT 'C', 16, 'Strengtheners in Fabric 伸度不足', 16
    -- D : SEWING PROCESS
    UNION ALL SELECT 'D', 17, 'Thread is Broken 縫い糸切れ', 17
    UNION ALL SELECT 'D', 18, 'Seam Defect 縫いはずれ', 18
    UNION ALL SELECT 'D', 19, 'Missing Stitch 縫い忘れ', 19
    UNION ALL SELECT 'D', 20, 'Drop Stitch 縫い落ち', 20
    UNION ALL SELECT 'D', 21, 'Skip Stitch 目飛び', 21
    UNION ALL SELECT 'D', 22, 'Needle Hole 針落ち痕', 22
    UNION ALL SELECT 'D', 23, 'Thread tension loosed 糸調子不良', 23
    UNION ALL SELECT 'D', 24, 'Bad Sewing 縫製不良', 24
    -- E : ACCESSORY
    UNION ALL SELECT 'E', 25, 'Accessory Wrong Attach 付け位置違い', 25
    UNION ALL SELECT 'E', 26, 'Accessory Mistake 取付け不良', 26
    UNION ALL SELECT 'E', 27, 'Accessory Damaging 材質不良', 27
    UNION ALL SELECT 'E', 28, 'Accessory Missing 付け忘れ，脱落', 28
    -- F : OTHER
    UNION ALL SELECT 'F', 29, 'Uncut Thread 糸始末不良', 29
    UNION ALL SELECT 'F', 30, 'QC Sticker Appear シール取り忘れ', 30
    UNION ALL SELECT 'F', 31, 'Others その他', 31
) AS items
WHERE dt.name = 'TEMPLATE_31'
  AND dc.code = items.category_code;


-- =============================================================================
-- TEMPLATE_37  (37 items)
-- =============================================================================

-- ── Categories ────────────────────────────────────────────────────────────────
INSERT OR IGNORE INTO defect_categories (template_id, code, label, sort_order)
SELECT t37.id, cats.code, cats.label, cats.sort_order
FROM (SELECT id FROM defect_templates WHERE name = 'TEMPLATE_37') t37
CROSS JOIN (
    SELECT 'A' AS code, '素材不良 Material Defects' AS label, 1 AS sort_order
    UNION ALL SELECT 'B', '縫製不良 Sewing Defects', 2
    UNION ALL SELECT 'C', '付属不良 Trim Defects', 3
    UNION ALL SELECT 'D', '仕上げ不良 Finishing Defects', 4
    UNION ALL SELECT 'E', '他 Others', 5
) AS cats;

-- ── Items ─────────────────────────────────────────────────────────────────────
INSERT OR IGNORE INTO defect_items_def (category_id, item_no, name, sort_order)
SELECT dc.id, items.item_no, items.name, items.sort_order
FROM defect_categories dc
JOIN defect_templates dt ON dc.template_id = dt.id
CROSS JOIN (
    SELECT 'A' AS category_code, 1 AS item_no, 'Nep, slub, fly' AS name, 1 AS sort_order
    UNION ALL SELECT 'A', 2, 'Holes, scratches, tears', 2
    UNION ALL SELECT 'A', 3, 'Uneven Dyeing, Color shading,warp/weft streak', 3
    UNION ALL SELECT 'A', 4, 'Poor Texture, Bad handfeel, Bad surface', 4
    UNION ALL SELECT 'A', 5, 'Skew', 5
    UNION ALL SELECT 'A', 6, 'Bad smell/ Odor', 6
    UNION ALL SELECT 'A', 7, 'Other', 7
    UNION ALL SELECT 'B', 8, 'Poor Shape (Bad form), non-symmetrical, dislocation', 8
    UNION ALL SELECT 'B', 9, 'Poor Joining of pattern/ Poor print/embroidery', 9
    UNION ALL SELECT 'B', 10, 'Staggered seams,spirality,wrinkles', 10
    UNION ALL SELECT 'B', 11, 'Puckering, gathered stitching', 11
    UNION ALL SELECT 'B', 12, 'Broken Stitches/ Broken Seam', 12
    UNION ALL SELECT 'B', 13, 'Broken Material ( From Stitching)', 13
    UNION ALL SELECT 'B', 14, 'Insufficient stretch in seams', 14
    UNION ALL SELECT 'B', 15, 'Poor stitch length, poor thred tension', 15
    UNION ALL SELECT 'B', 16, 'Insufficient seam allowance, run-off stitches', 16
    UNION ALL SELECT 'B', 17, 'Needle marks, restitched seams', 17
    UNION ALL SELECT 'B', 18, 'Exposed lining', 18
    UNION ALL SELECT 'B', 19, 'Skipped stitches', 19
    UNION ALL SELECT 'B', 20, 'Sewn by mistake, puckered seams,pleated', 20
    UNION ALL SELECT 'B', 21, 'Missing stitches, missing bartacks', 21
    UNION ALL SELECT 'B', 22, 'Insufficient strength /Bad reinforce stitch', 22
    UNION ALL SELECT 'B', 23, 'Other', 23
    UNION ALL SELECT 'C', 24, 'Poor Quality (faded,burred,rusty,dirty)', 24
    UNION ALL SELECT 'C', 25, 'Poorly attached trim (deformed,damaged)', 25
    UNION ALL SELECT 'C', 26, 'Missing Trim ( detached)', 26
    UNION ALL SELECT 'C', 27, 'Misplaced/ incorrect trim', 27
    UNION ALL SELECT 'C', 28, 'Poorly functioning', 28
    UNION ALL SELECT 'D', 29, 'Bad thread trimming ,lint ( thread end left)', 29
    UNION ALL SELECT 'D', 30, 'Dirty, Stains', 30
    UNION ALL SELECT 'D', 31, 'Poor shape, Bad form, non-symmetrical', 31
    UNION ALL SELECT 'D', 32, 'Shining mark, wrinkles', 32
    UNION ALL SELECT 'D', 33, 'Poor wash Treatment', 33
    UNION ALL SELECT 'D', 34, 'Poor Measurment /wrong Measurement', 34
    UNION ALL SELECT 'E', 35, 'Poor Packaging', 35
    UNION ALL SELECT 'E', 36, 'Wrong quantity Packed', 36
    UNION ALL SELECT 'E', 37, 'Other', 37
) AS items
WHERE dt.name = 'TEMPLATE_37'
  AND dc.code = items.category_code;


-- =============================================================================
-- TEMPLATE_78  (78 items)
-- =============================================================================

-- ── Categories ────────────────────────────────────────────────────────────────
INSERT OR IGNORE INTO defect_categories (template_id, code, label, sort_order)
SELECT t78.id, cats.code, cats.label, cats.sort_order
FROM (SELECT id FROM defect_templates WHERE name = 'TEMPLATE_78') t78
CROSS JOIN (
    SELECT 'A' AS code, 'Fabrics' AS label, 1 AS sort_order
    UNION ALL SELECT 'B', 'Sewing', 2
    UNION ALL SELECT 'C', 'ACC', 3
    UNION ALL SELECT 'D', 'Finish', 4
    UNION ALL SELECT 'E', 'Safety', 5
    UNION ALL SELECT 'F', 'Others', 6
) AS cats;

-- ── Items ─────────────────────────────────────────────────────────────────────
INSERT OR IGNORE INTO defect_items_def (category_id, item_no, name, sort_order)
SELECT dc.id, items.item_no, items.name, items.sort_order
FROM defect_categories dc
JOIN defect_templates dt ON dc.template_id = dt.id
CROSS JOIN (
    -- A : Fabrics
    SELECT 'A' AS category_code, 1 AS item_no, 'Damage' AS name, 1 AS sort_order
    UNION ALL SELECT 'A', 2, 'Needle breakage defect', 2
    UNION ALL SELECT 'A', 3, 'Hole, tear', 3
    UNION ALL SELECT 'A', 4, 'NEP', 4
    UNION ALL SELECT 'A', 5, 'SLUB', 5
    UNION ALL SELECT 'A', 6, 'Weft defect', 6
    UNION ALL SELECT 'A', 7, 'Unexpected things interwoven', 7
    UNION ALL SELECT 'A', 8, 'Bowing', 8
    UNION ALL SELECT 'A', 9, 'Odor', 9
    UNION ALL SELECT 'A', 10, 'Uneven dyeing', 10
    UNION ALL SELECT 'A', 11, 'Texture, surface defect', 11
    UNION ALL SELECT 'A', 12, 'Warp and weft defect', 12
    -- B : Sewing
    UNION ALL SELECT 'B', 1, 'Hue difference', 13
    UNION ALL SELECT 'B', 2, 'Unevenness', 14
    UNION ALL SELECT 'B', 3, 'Pieces not symmetrical', 15
    UNION ALL SELECT 'B', 4, 'Deformation (Defect in shape)', 16
    UNION ALL SELECT 'B', 5, 'Tight or loose part of fabric', 17
    UNION ALL SELECT 'B', 6, 'Uneven seam', 18
    UNION ALL SELECT 'B', 7, 'Spiralty, wrinkle', 19
    UNION ALL SELECT 'B', 8, 'PUCKERING', 20
    UNION ALL SELECT 'B', 9, 'Corrugation', 21
    UNION ALL SELECT 'B', 10, 'Thread breakage', 22
    UNION ALL SELECT 'B', 11, 'Lack of elasticity', 23
    UNION ALL SELECT 'B', 12, 'Incorrect stitching number', 24
    UNION ALL SELECT 'B', 13, 'Stitches out of seam allowance', 25
    UNION ALL SELECT 'B', 14, 'Missing stitch', 26
    UNION ALL SELECT 'B', 15, 'Lack of seam allowance', 27
    UNION ALL SELECT 'B', 16, 'Unexpected tuck', 28
    UNION ALL SELECT 'B', 17, 'Unexpected fullness', 29
    UNION ALL SELECT 'B', 18, 'Needle mark', 30
    UNION ALL SELECT 'B', 19, 'Sewing defects caused by machine', 31
    UNION ALL SELECT 'B', 20, 'Incorrect size of lining', 32
    UNION ALL SELECT 'B', 21, 'Skipped stitch', 33
    UNION ALL SELECT 'B', 22, 'Sewing involving unexpected parts', 34
    UNION ALL SELECT 'B', 23, 'Missing sewing process', 35
    UNION ALL SELECT 'B', 24, 'Mislocated bar-tack', 36
    UNION ALL SELECT 'B', 25, 'Incorrect thread tension', 37
    UNION ALL SELECT 'B', 26, 'Falling off of a thread', 38
    UNION ALL SELECT 'B', 27, 'Lack of reverse stitch', 39
    UNION ALL SELECT 'B', 28, 'Incorrect easing', 40
    UNION ALL SELECT 'B', 29, 'Piecing defect', 41
    UNION ALL SELECT 'B', 30, 'Incorrect lapped seam', 42
    UNION ALL SELECT 'B', 31, 'Incorrect trimming', 43
    UNION ALL SELECT 'B', 32, 'Lack of strength', 44
    UNION ALL SELECT 'B', 33, 'Incorrect buttonhole sewing', 45
    UNION ALL SELECT 'B', 34, 'Incorrect brand label sewing', 46
    UNION ALL SELECT 'B', 35, 'Sewing slip', 47
    UNION ALL SELECT 'B', 36, 'Incorrect position', 48
    UNION ALL SELECT 'B', 37, 'Incorrect pattern matching', 49
    UNION ALL SELECT 'B', 38, 'Peel off glue/delamination', 50
    UNION ALL SELECT 'B', 39, 'Visible/see through glue', 51
    UNION ALL SELECT 'B', 40, 'Bonding seam uneven/wavy', 52
    UNION ALL SELECT 'B', 41, 'Bonding seam not catch up/bad selvaged', 53
    UNION ALL SELECT 'B', 42, 'Stick glue/leaking glue', 54
    UNION ALL SELECT 'B', 43, 'Mold Shape', 55
    UNION ALL SELECT 'B', 44, 'Poor application glue position', 56
    UNION ALL SELECT 'B', 45, 'Yarn severance', 57
    -- C : ACC
    UNION ALL SELECT 'C', 1, 'Unsecured rivet and snap buttons', 58
    UNION ALL SELECT 'C', 2, 'Incorrect swaging', 59
    UNION ALL SELECT 'C', 3, 'Falling off of buttons', 60
    UNION ALL SELECT 'C', 4, 'Burr', 61
    UNION ALL SELECT 'C', 5, 'Incorrect zippers', 62
    UNION ALL SELECT 'C', 6, 'Incorrect indication of sub materials', 63
    UNION ALL SELECT 'C', 7, 'Incorrect quality of materials', 64
    UNION ALL SELECT 'C', 8, 'Missing accessories', 65
    UNION ALL SELECT 'C', 9, 'Adhesive interlining', 66
    -- D : Finish
    UNION ALL SELECT 'D', 1, 'Dust, lint', 67
    UNION ALL SELECT 'D', 2, 'Smear, stain', 68
    UNION ALL SELECT 'D', 3, 'Size', 69
    UNION ALL SELECT 'D', 4, 'Peel off and misalignment of prints', 70
    UNION ALL SELECT 'D', 5, 'Pressure mark', 71
    UNION ALL SELECT 'D', 6, 'Wash finish', 72
    -- E : Safety
    UNION ALL SELECT 'E', 1, 'Thread', 73
    UNION ALL SELECT 'E', 2, 'Hazardous object/ foreign bodies', 74
    UNION ALL SELECT 'E', 3, 'Odor', 75
    -- F : Others
    UNION ALL SELECT 'F', 1, 'Bad packing', 76
    UNION ALL SELECT 'F', 2, 'Wrong quantity packed', 77
    UNION ALL SELECT 'F', 3, 'Others', 78
) AS items
WHERE dt.name = 'TEMPLATE_78'
  AND dc.code = items.category_code;