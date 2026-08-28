\set ON_ERROR_STOP on
\pset pager off
SET client_encoding = 'UTF8';

BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

-- Lock every row in the approved scope before checking its old state.
SELECT id FROM schedule_activities
 WHERE id IN (
   'cc5a2014-e13b-4d5f-8722-1d739f0d824f',
   'd905f512-ac74-45cf-98eb-b04cc779d5aa'
 ) FOR UPDATE;
SELECT id FROM story_arcs
 WHERE id = '6f727ca8102c493faf8af57344b6a7ae' FOR UPDATE;
SELECT id FROM story_arc_beats
 WHERE id IN (
   '902e079dfba24e0a83fa7b33d4a92f6b',
   '8a27eccf52a34ff9bf201113bdc81a73',
   '3364666069e5424fbf0e5d9a5faffb37'
 ) FOR UPDATE;
SELECT id FROM character_goals
 WHERE id = 'd7196950-1d60-4f07-b8a6-eb7bdff073ee' FOR UPDATE;
SELECT id FROM pending_follow_ups
 WHERE id IN (
   '60a72461-99f6-46b1-846d-0f54b144f4e7',
   'ff0cbb60-3a04-4df1-9b93-d2ea8dfd1b48',
   '31f898bd-36cd-4d54-8597-11ce5ce7f70f',
   '29ea8f5e-2a21-41c5-9b23-ccc624bf23e2',
   'a0a025a8-8be4-4c39-bcc8-90676795d2d7'
 ) FOR UPDATE;

DO $preflight$
DECLARE n integer;
BEGIN
  SELECT count(*) INTO n
    FROM schedule_activities sa
    JOIN daily_schedules ds ON ds.id = sa.schedule_id
   WHERE sa.id = 'cc5a2014-e13b-4d5f-8722-1d739f0d824f'
     AND ds.character_id = '8b491064-97af-43b1-9124-c89977406120'
     AND ds.id = '99abb38c-fd76-440f-b5bb-2bfb9f2ab724'
     AND ds.date = '2026-08-30'
     AND sa.start_at = TIMESTAMPTZ '2026-08-30 09:30:00+00'
     AND sa.end_at = TIMESTAMPTZ '2026-08-30 10:00:00+00'
     AND sa.memorialized IS FALSE
     AND sa.commitment_key IS NULL
     AND sa.is_first_meeting IS FALSE;
  IF n <> 1 THEN RAISE EXCEPTION 'meet activity precondition failed (%)', n; END IF;

  SELECT count(*) INTO n
    FROM schedule_activities sa
    JOIN daily_schedules ds ON ds.id = sa.schedule_id
   WHERE sa.id = 'd905f512-ac74-45cf-98eb-b04cc779d5aa'
     AND ds.character_id = '8b491064-97af-43b1-9124-c89977406120'
     AND ds.id = '99abb38c-fd76-440f-b5bb-2bfb9f2ab724'
     AND ds.date = '2026-08-30'
     AND sa.start_at = TIMESTAMPTZ '2026-08-30 10:00:00+00'
     AND sa.end_at = TIMESTAMPTZ '2026-08-30 13:30:00+00'
     AND sa.memorialized IS FALSE
     AND sa.commitment_key IS NULL
     AND sa.is_first_meeting IS FALSE;
  IF n <> 1 THEN RAISE EXCEPTION 'festival activity precondition failed (%)', n; END IF;

  SELECT count(*) INTO n
    FROM story_arcs
   WHERE id = '6f727ca8102c493faf8af57344b6a7ae'
     AND character_id = '8b491064-97af-43b1-9124-c89977406120'
     AND status = 'active'
     AND premise LIKE '%2026-08-31%'
     AND (length(premise) - length(replace(premise, '2026-08-31', ''))) / 10 = 2;
  IF n <> 1 THEN RAISE EXCEPTION 'arc premise precondition failed (%)', n; END IF;

  SELECT count(*) INTO n FROM story_arc_beats
   WHERE id = '902e079dfba24e0a83fa7b33d4a92f6b'
     AND arc_id = '6f727ca8102c493faf8af57344b6a7ae'
     AND sequence = 5 AND scheduled_date = '2026-08-30'
     AND status = 'pending' AND commitment_key IS NULL
     AND is_first_meeting IS FALSE;
  IF n <> 1 THEN RAISE EXCEPTION 'beat 902 precondition failed (%)', n; END IF;

  SELECT count(*) INTO n FROM story_arc_beats
   WHERE id = '8a27eccf52a34ff9bf201113bdc81a73'
     AND arc_id = '6f727ca8102c493faf8af57344b6a7ae'
     AND sequence = 6 AND scheduled_date = '2026-08-30'
     AND status = 'pending' AND commitment_key IS NULL
     AND is_first_meeting IS FALSE;
  IF n <> 1 THEN RAISE EXCEPTION 'beat 8a27 precondition failed (%)', n; END IF;

  SELECT count(*) INTO n FROM story_arc_beats
   WHERE id = '3364666069e5424fbf0e5d9a5faffb37'
     AND arc_id = '6f727ca8102c493faf8af57344b6a7ae'
     AND sequence = 9 AND scheduled_date = '2026-08-30'
     AND status = 'pending' AND commitment_key IS NULL
     AND is_first_meeting IS FALSE;
  IF n <> 1 THEN RAISE EXCEPTION 'beat 336 precondition failed (%)', n; END IF;

  SELECT count(*) INTO n FROM character_goals
   WHERE id = 'd7196950-1d60-4f07-b8a6-eb7bdff073ee'
     AND character_id = '8b491064-97af-43b1-9124-c89977406120'
     AND status = 'active' AND commitment_key IS NULL
     AND target_date_iso IS NULL
     AND content LIKE '%2026-08-31%';
  IF n <> 1 THEN RAISE EXCEPTION 'goal precondition failed (%)', n; END IF;

  SELECT count(*) INTO n FROM pending_follow_ups
   WHERE id = '60a72461-99f6-46b1-846d-0f54b144f4e7'
     AND character_id = '8b491064-97af-43b1-9124-c89977406120'
     AND status = 'queued' AND kind = 'scheduled_promise'
     AND commitment_key IS NULL
     AND scheduled_for = TIMESTAMPTZ '2026-08-30 06:00:00+00';
  IF n <> 1 THEN RAISE EXCEPTION 'promise 60 precondition failed (%)', n; END IF;

  SELECT count(*) INTO n FROM pending_follow_ups
   WHERE id = 'ff0cbb60-3a04-4df1-9b93-d2ea8dfd1b48'
     AND character_id = '8b491064-97af-43b1-9124-c89977406120'
     AND status = 'queued' AND kind = 'scheduled_promise'
     AND commitment_key IS NULL
     AND scheduled_for = TIMESTAMPTZ '2026-08-30 08:30:00+00';
  IF n <> 1 THEN RAISE EXCEPTION 'promise ff precondition failed (%)', n; END IF;

  SELECT count(*) INTO n FROM pending_follow_ups
   WHERE id = '31f898bd-36cd-4d54-8597-11ce5ce7f70f'
     AND character_id = '8b491064-97af-43b1-9124-c89977406120'
     AND status = 'queued' AND kind = 'scheduled_promise'
     AND commitment_key IS NULL
     AND scheduled_for = TIMESTAMPTZ '2026-08-30 10:00:00+00';
  IF n <> 1 THEN RAISE EXCEPTION 'delete promise 31f precondition failed (%)', n; END IF;

  SELECT count(*) INTO n FROM pending_follow_ups
   WHERE id = '29ea8f5e-2a21-41c5-9b23-ccc624bf23e2'
     AND character_id = '8b491064-97af-43b1-9124-c89977406120'
     AND status = 'queued' AND kind = 'scheduled_promise'
     AND commitment_key IS NULL
     AND scheduled_for = TIMESTAMPTZ '2026-08-31 04:00:00+00';
  IF n <> 1 THEN RAISE EXCEPTION 'delete promise 29ea precondition failed (%)', n; END IF;

  SELECT count(*) INTO n FROM pending_follow_ups
   WHERE id = 'a0a025a8-8be4-4c39-bcc8-90676795d2d7'
     AND character_id = '8b491064-97af-43b1-9124-c89977406120'
     AND status = 'queued' AND kind = 'scheduled_promise'
     AND commitment_key IS NULL
     AND scheduled_for = TIMESTAMPTZ '2026-08-31 06:00:00+00';
  IF n <> 1 THEN RAISE EXCEPTION 'delete promise a0 precondition failed (%)', n; END IF;

  IF EXISTS (
    SELECT 1 FROM outbound_message_deliveries d
     WHERE d.payload_json LIKE ANY (ARRAY[
       '%31f898bd-36cd-4d54-8597-11ce5ce7f70f%',
       '%29ea8f5e-2a21-41c5-9b23-ccc624bf23e2%',
       '%a0a025a8-8be4-4c39-bcc8-90676795d2d7%'
     ])
  ) THEN RAISE EXCEPTION 'outbound dependency found'; END IF;

  IF EXISTS (
    SELECT 1 FROM schedule_activities sa
    JOIN daily_schedules ds ON ds.id = sa.schedule_id
    WHERE ds.character_id = '8b491064-97af-43b1-9124-c89977406120'
      AND sa.memorialized IS FALSE AND sa.is_first_meeting IS TRUE
  ) THEN RAISE EXCEPTION 'unexpected live schedule first-meeting flag'; END IF;

  IF EXISTS (
    SELECT 1 FROM story_arc_beats sab
    JOIN story_arcs arc ON arc.id = sab.arc_id
    WHERE arc.character_id = '8b491064-97af-43b1-9124-c89977406120'
      AND sab.status IN ('pending', 'active')
      AND sab.is_first_meeting IS TRUE
  ) THEN RAISE EXCEPTION 'unexpected live story first-meeting flag'; END IF;

  IF EXISTS (SELECT 1 FROM schedule_activities WHERE commitment_key IN ('REVIEW-MEET-20260830', 'REVIEW-FESTIVAL-20260830'))
    OR EXISTS (SELECT 1 FROM story_arc_beats WHERE commitment_key IN ('REVIEW-MEET-20260830', 'REVIEW-FESTIVAL-20260830'))
    OR EXISTS (SELECT 1 FROM character_goals WHERE commitment_key IN ('REVIEW-MEET-20260830', 'REVIEW-FESTIVAL-20260830'))
    OR EXISTS (SELECT 1 FROM pending_follow_ups WHERE commitment_key IN ('REVIEW-MEET-20260830', 'REVIEW-FESTIVAL-20260830'))
  THEN RAISE EXCEPTION 'approved commitment key already in use'; END IF;
END
$preflight$;

-- Approved live projections. Every exact-ID write must affect exactly one row.
DO $mutate$
DECLARE n integer;
BEGIN
  UPDATE schedule_activities
     SET commitment_key = 'REVIEW-MEET-20260830', is_first_meeting = TRUE
   WHERE id = 'cc5a2014-e13b-4d5f-8722-1d739f0d824f';
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN RAISE EXCEPTION 'meet activity update affected % rows', n; END IF;

  UPDATE schedule_activities
     SET commitment_key = 'REVIEW-FESTIVAL-20260830', is_first_meeting = FALSE
   WHERE id = 'd905f512-ac74-45cf-98eb-b04cc779d5aa';
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN RAISE EXCEPTION 'festival activity update affected % rows', n; END IF;

  UPDATE story_arc_beats
     SET commitment_key = 'REVIEW-MEET-20260830', is_first_meeting = TRUE
   WHERE id = '3364666069e5424fbf0e5d9a5faffb37';
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN RAISE EXCEPTION 'meet beat update affected % rows', n; END IF;

  UPDATE story_arcs
     SET premise = replace(premise, '2026-08-31', '2026-08-30'),
         updated_at = clock_timestamp()
   WHERE id = '6f727ca8102c493faf8af57344b6a7ae';
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN RAISE EXCEPTION 'arc premise update affected % rows', n; END IF;

  -- The approved old research/meeting goal is removed as one exact row.
  DELETE FROM character_goals
   WHERE id = 'd7196950-1d60-4f07-b8a6-eb7bdff073ee';
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN RAISE EXCEPTION 'goal delete affected % rows', n; END IF;

  -- Keep delivery windows, bind the two queued promises, and refresh their
  -- derived dedupe identity after changing the intent text.
  UPDATE pending_follow_ups
     SET promise_intent = '出發前先和玩家聊聊親手交付深灰色卡片的期待',
         commitment_key = 'REVIEW-MEET-20260830',
         dedupe_key = 'fcb58e96922c075d2e88eefad7a0435ef96a03041663f589b990e8fb53c74829',
         delivery_slot_key = '477b1a323e7669e47c9ce56619dc548133ac92c4b23d8ce25bfbb4ae0008a8e7',
         updated_at = clock_timestamp()
   WHERE id = '60a72461-99f6-46b1-846d-0f54b144f4e7';
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN RAISE EXCEPTION 'promise 60 update affected % rows', n; END IF;

  UPDATE pending_follow_ups
     SET promise_intent = '確認玩家是否快到達並完成報到，接著一起參加香港森境Online線下夏祭',
         commitment_key = 'REVIEW-FESTIVAL-20260830',
         dedupe_key = '07e3857489e7df0fc38d9089dd629335256eaca0239781f2c67f977fcb2f8f40',
         delivery_slot_key = 'b24fd0e5a3e06aa9bc69d11c8a5662839dbcdd53a402d7eab0e9812b4f58e58b',
         updated_at = clock_timestamp()
   WHERE id = 'ff0cbb60-3a04-4df1-9b93-d2ea8dfd1b48';
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN RAISE EXCEPTION 'promise ff update affected % rows', n; END IF;

  DELETE FROM pending_follow_ups
   WHERE id IN (
     '31f898bd-36cd-4d54-8597-11ce5ce7f70f',
     '29ea8f5e-2a21-41c5-9b23-ccc624bf23e2',
     'a0a025a8-8be4-4c39-bcc8-90676795d2d7'
   );
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 3 THEN RAISE EXCEPTION 'duplicate promise delete affected % rows', n; END IF;
END
$mutate$;

DO $postcheck$
DECLARE n integer;
BEGIN
  SELECT count(*) INTO n FROM schedule_activities
   WHERE id = 'cc5a2014-e13b-4d5f-8722-1d739f0d824f'
     AND commitment_key = 'REVIEW-MEET-20260830' AND is_first_meeting IS TRUE;
  IF n <> 1 THEN RAISE EXCEPTION 'meet activity postcondition failed'; END IF;
  SELECT count(*) INTO n FROM schedule_activities
   WHERE id = 'd905f512-ac74-45cf-98eb-b04cc779d5aa'
     AND commitment_key = 'REVIEW-FESTIVAL-20260830' AND is_first_meeting IS FALSE;
  IF n <> 1 THEN RAISE EXCEPTION 'festival activity postcondition failed'; END IF;
  SELECT count(*) INTO n FROM story_arc_beats
   WHERE id = '3364666069e5424fbf0e5d9a5faffb37'
     AND commitment_key = 'REVIEW-MEET-20260830' AND is_first_meeting IS TRUE;
  IF n <> 1 THEN RAISE EXCEPTION 'meet beat postcondition failed'; END IF;
  SELECT count(*) INTO n FROM story_arcs
   WHERE id = '6f727ca8102c493faf8af57344b6a7ae'
     AND (length(premise) - length(replace(premise, '2026-08-30', ''))) / 10 >= 2
     AND premise NOT LIKE '%2026-08-31%';
  IF n <> 1 THEN RAISE EXCEPTION 'arc premise postcondition failed'; END IF;
  SELECT count(*) INTO n FROM pending_follow_ups
   WHERE id = '60a72461-99f6-46b1-846d-0f54b144f4e7'
     AND status = 'queued' AND commitment_key = 'REVIEW-MEET-20260830'
     AND dedupe_key = 'fcb58e96922c075d2e88eefad7a0435ef96a03041663f589b990e8fb53c74829';
  IF n <> 1 THEN RAISE EXCEPTION 'promise 60 postcondition failed'; END IF;
  SELECT count(*) INTO n FROM pending_follow_ups
   WHERE id = 'ff0cbb60-3a04-4df1-9b93-d2ea8dfd1b48'
     AND status = 'queued' AND commitment_key = 'REVIEW-FESTIVAL-20260830'
     AND dedupe_key = '07e3857489e7df0fc38d9089dd629335256eaca0239781f2c67f977fcb2f8f40';
  IF n <> 1 THEN RAISE EXCEPTION 'promise ff postcondition failed'; END IF;
  IF EXISTS (SELECT 1 FROM pending_follow_ups WHERE id IN ('31f898bd-36cd-4d54-8597-11ce5ce7f70f','29ea8f5e-2a21-41c5-9b23-ccc624bf23e2','a0a025a8-8be4-4c39-bcc8-90676795d2d7'))
    THEN RAISE EXCEPTION 'duplicate promises remain'; END IF;
  IF EXISTS (SELECT 1 FROM character_goals WHERE id = 'd7196950-1d60-4f07-b8a6-eb7bdff073ee')
    THEN RAISE EXCEPTION 'deleted goal remains'; END IF;
  SELECT count(*) INTO n FROM schedule_activities sa JOIN daily_schedules ds ON ds.id = sa.schedule_id
   WHERE ds.character_id = '8b491064-97af-43b1-9124-c89977406120'
     AND sa.memorialized IS FALSE AND sa.is_first_meeting IS TRUE;
  IF n <> 1 THEN RAISE EXCEPTION 'live schedule first-meeting count is %', n; END IF;
  SELECT count(*) INTO n FROM story_arc_beats sab JOIN story_arcs arc ON arc.id = sab.arc_id
   WHERE arc.character_id = '8b491064-97af-43b1-9124-c89977406120'
     AND sab.status IN ('pending', 'active') AND sab.is_first_meeting IS TRUE;
  IF n <> 1 THEN RAISE EXCEPTION 'live story first-meeting count is %', n; END IF;
END
$postcheck$;

SELECT 'LEGACY_REPAIR_COMMITTED' AS result;
COMMIT;
