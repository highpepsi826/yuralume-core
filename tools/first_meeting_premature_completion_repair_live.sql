\set ON_ERROR_STOP on
\pset pager off
SET client_encoding = 'UTF8';

-- Approved one-shot repair for the false unattended first-meeting event.
-- This file deliberately has no fuzzy matches: every target is an exact ID
-- plus current-state preconditions. Run only after the app is stopped and a
-- new verified custom-format dump exists.

BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

-- Lock the exact write set and the live schedule anchor before checking it.
SELECT id FROM story_arcs
 WHERE id = '6f727ca8102c493faf8af57344b6a7ae'
 FOR UPDATE;
SELECT id FROM story_arc_beats
 WHERE id = '3364666069e5424fbf0e5d9a5faffb37'
 FOR UPDATE;
SELECT id FROM story_events
 WHERE id = 'bca2f515-efa8-48ef-928a-8574f26a3fa4'
 FOR UPDATE;
SELECT id FROM memory_items
 WHERE id IN (
   '8adddf35-75ac-42e6-8ba6-45250eba7099',
   '7abf826c-546f-44da-8d55-a34d161db505'
 )
 FOR UPDATE;
SELECT sa.id
  FROM schedule_activities sa
  JOIN daily_schedules ds ON ds.id = sa.schedule_id
 WHERE sa.id = 'cc5a2014-e13b-4d5f-8722-1d739f0d824f'
 FOR UPDATE;

DO $preflight$
DECLARE
  n integer;
BEGIN
  -- The correct 17:30 HK first-meeting activity must remain live and unique.
  SELECT count(*) INTO n
    FROM schedule_activities sa
    JOIN daily_schedules ds ON ds.id = sa.schedule_id
   WHERE sa.id = 'cc5a2014-e13b-4d5f-8722-1d739f0d824f'
     AND ds.id = '99abb38c-fd76-440f-b5bb-2bfb9f2ab724'
     AND ds.character_id = '8b491064-97af-43b1-9124-c89977406120'
     AND ds.date = '2026-08-30'
     AND sa.start_at = TIMESTAMPTZ '2026-08-30 09:30:00+00'
     AND sa.end_at = TIMESTAMPTZ '2026-08-30 10:00:00+00'
     AND sa.memorialized IS FALSE
     AND sa.commitment_key = 'REVIEW-MEET-20260830'
     AND sa.is_first_meeting IS TRUE
     AND sa.source_beat_id IS NULL;
  IF n <> 1 THEN
    RAISE EXCEPTION 'live first-meeting schedule precondition failed (%)', n;
  END IF;

  SELECT count(*) INTO n
    FROM schedule_activities sa
    JOIN daily_schedules ds ON ds.id = sa.schedule_id
   WHERE ds.character_id = '8b491064-97af-43b1-9124-c89977406120'
     AND ds.date = '2026-08-30'
     AND sa.memorialized IS FALSE
     AND sa.commitment_key = 'REVIEW-MEET-20260830'
     AND sa.is_first_meeting IS TRUE;
  IF n <> 1 THEN
    RAISE EXCEPTION 'live first-meeting schedule anchor is not unique (%)', n;
  END IF;

  -- Keep the separate 18:00 HK festival activity intact; it is not written.
  SELECT count(*) INTO n
    FROM schedule_activities sa
    JOIN daily_schedules ds ON ds.id = sa.schedule_id
   WHERE sa.id = 'd905f512-ac74-45cf-98eb-b04cc779d5aa'
     AND ds.id = '99abb38c-fd76-440f-b5bb-2bfb9f2ab724'
     AND ds.character_id = '8b491064-97af-43b1-9124-c89977406120'
     AND ds.date = '2026-08-30'
     AND sa.start_at = TIMESTAMPTZ '2026-08-30 10:00:00+00'
     AND sa.end_at = TIMESTAMPTZ '2026-08-30 13:30:00+00'
     AND sa.memorialized IS FALSE
     AND sa.commitment_key = 'REVIEW-FESTIVAL-20260830'
     AND sa.is_first_meeting IS FALSE;
  IF n <> 1 THEN
    RAISE EXCEPTION 'festival schedule precondition failed (%)', n;
  END IF;

  SELECT count(*) INTO n
    FROM story_arcs
   WHERE id = '6f727ca8102c493faf8af57344b6a7ae'
     AND character_id = '8b491064-97af-43b1-9124-c89977406120'
     AND status = 'completed'
     AND md5(title) = 'e3efe8ac70b9223e2035bdba8eb37a5f'
     AND md5(premise) = '03cfa9f70d438ae931d38527effe6be6';
  IF n <> 1 THEN
    RAISE EXCEPTION 'target arc precondition failed (%)', n;
  END IF;

  SELECT count(*) INTO n
    FROM story_arc_beats
   WHERE id = '3364666069e5424fbf0e5d9a5faffb37'
     AND arc_id = '6f727ca8102c493faf8af57344b6a7ae'
     AND sequence = 9
     AND scheduled_date = '2026-08-30'
     AND status = 'realized'
     AND realized_event_id = 'bca2f515-efa8-48ef-928a-8574f26a3fa4'
     AND play_attempt_count = 1
     AND last_play_attempt_at = TIMESTAMPTZ '2026-08-29 16:02:03.051074+00'
     AND last_play_attempt_source = 'scene_simulation'
     AND last_play_attempt_result = 'realized'
     AND last_play_push_intensity = 'autonomous_scene'
     AND play_failure_count = 0
     AND last_play_failure_at IS NULL
     AND operator_position IS NULL
     AND commitment_key = 'REVIEW-MEET-20260830'
     AND is_first_meeting IS TRUE
     AND md5(title) = 'b45fac84bb2f7f4ea27bccf076136d4c'
     AND md5(summary) = 'ed5fb463e8ac38747a59edbfc304ea26';
  IF n <> 1 THEN
    RAISE EXCEPTION 'target first-meeting beat precondition failed (%)', n;
  END IF;

  -- The arc had no other pending beat when it became completed.
  SELECT count(*) INTO n
    FROM story_arc_beats
   WHERE arc_id = '6f727ca8102c493faf8af57344b6a7ae'
     AND status = 'realized';
  IF n <> 14 THEN
    RAISE EXCEPTION 'target arc realized-beat count precondition failed (%)', n;
  END IF;

  SELECT count(*) INTO n
    FROM story_events
   WHERE id = 'bca2f515-efa8-48ef-928a-8574f26a3fa4'
     AND character_id = '8b491064-97af-43b1-9124-c89977406120'
     AND date = '2026-08-30'
     AND seed_id IS NULL
     AND arc_beat_id IS NULL
     AND memorialized IS TRUE
     AND created_at = TIMESTAMPTZ '2026-08-29 16:02:13.568068+00'
     AND md5(narrative) = '94397e968e0bea2bf175a74eea304ea9';
  IF n <> 1 THEN
    RAISE EXCEPTION 'false story-event precondition failed (%)', n;
  END IF;

  SELECT count(*) INTO n
    FROM memory_items
   WHERE id = '8adddf35-75ac-42e6-8ba6-45250eba7099'
     AND character_id = '8b491064-97af-43b1-9124-c89977406120'
     AND kind = 'relationship_milestone'
     AND salience = 0.9
     AND created_at = TIMESTAMPTZ '2026-08-29 16:02:13.568068+00'
     AND md5(content) = '94397e968e0bea2bf175a74eea304ea9'
     AND tags LIKE '%arc_beat_id:3364666069e5424fbf0e5d9a5faffb37%';
  IF n <> 1 THEN
    RAISE EXCEPTION 'false beat-memory precondition failed (%)', n;
  END IF;

  SELECT count(*) INTO n
    FROM memory_items
   WHERE id = '7abf826c-546f-44da-8d55-a34d161db505'
     AND character_id = '8b491064-97af-43b1-9124-c89977406120'
     AND kind = 'relationship_milestone'
     AND salience = 0.95
     AND created_at = TIMESTAMPTZ '2026-08-30 06:21:12.976754+00'
     AND md5(content) = 'b202aac640c848c0b07488ae69d617e2'
     AND tags LIKE '%arc_completion:6f727ca8102c493faf8af57344b6a7ae%';
  IF n <> 1 THEN
    RAISE EXCEPTION 'false arc-completion memory precondition failed (%)', n;
  END IF;

  -- The two legitimate same-day stage events must still exist untouched.
  SELECT count(*) INTO n
    FROM story_events
   WHERE id IN (
     '4e04064e-4be7-48fb-b19a-92b57889b615',
     '0b487908-77f2-4f0b-808d-2da01a8824d2'
   )
     AND character_id = '8b491064-97af-43b1-9124-c89977406120'
     AND date = '2026-08-30';
  IF n <> 2 THEN
    RAISE EXCEPTION 'valid stage-event precondition failed (%)', n;
  END IF;
END
$preflight$;

DO $repair$
DECLARE
  n integer;
BEGIN
  -- Remove only the two artifacts of the false autonomous realization.
  DELETE FROM memory_items
   WHERE id IN (
     '8adddf35-75ac-42e6-8ba6-45250eba7099',
     '7abf826c-546f-44da-8d55-a34d161db505'
   );
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 2 THEN
    RAISE EXCEPTION 'false memory delete affected % rows', n;
  END IF;

  -- Unlink the beat before deleting the false event so it cannot retain a
  -- dangling canonical pointer even though the schema deliberately has no FK.
  UPDATE story_arc_beats
     SET status = 'pending',
         realized_event_id = NULL,
         play_attempt_count = 0,
         last_play_attempt_at = NULL,
         last_play_attempt_source = NULL,
         last_play_attempt_result = NULL,
         last_play_push_intensity = NULL,
         play_failure_count = 0,
         last_play_failure_at = NULL
   WHERE id = '3364666069e5424fbf0e5d9a5faffb37';
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN
    RAISE EXCEPTION 'first-meeting beat reset affected % rows', n;
  END IF;

  DELETE FROM story_events
   WHERE id = 'bca2f515-efa8-48ef-928a-8574f26a3fa4';
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN
    RAISE EXCEPTION 'false story-event delete affected % rows', n;
  END IF;

  UPDATE story_arcs
     SET status = 'active',
         updated_at = clock_timestamp()
   WHERE id = '6f727ca8102c493faf8af57344b6a7ae';
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN
    RAISE EXCEPTION 'target arc reopen affected % rows', n;
  END IF;
END
$repair$;

DO $postcheck$
DECLARE
  n integer;
BEGIN
  SELECT count(*) INTO n
    FROM story_arc_beats
   WHERE id = '3364666069e5424fbf0e5d9a5faffb37'
     AND status = 'pending'
     AND realized_event_id IS NULL
     AND play_attempt_count = 0
     AND last_play_attempt_at IS NULL
     AND last_play_attempt_source IS NULL
     AND last_play_attempt_result IS NULL
     AND last_play_push_intensity IS NULL
     AND play_failure_count = 0
     AND last_play_failure_at IS NULL
     AND commitment_key = 'REVIEW-MEET-20260830'
     AND is_first_meeting IS TRUE;
  IF n <> 1 THEN
    RAISE EXCEPTION 'first-meeting beat postcondition failed (%)', n;
  END IF;

  SELECT count(*) INTO n
    FROM story_arcs
   WHERE id = '6f727ca8102c493faf8af57344b6a7ae'
     AND status = 'active';
  IF n <> 1 THEN
    RAISE EXCEPTION 'target arc postcondition failed (%)', n;
  END IF;

  IF EXISTS (
    SELECT 1 FROM story_events
     WHERE id = 'bca2f515-efa8-48ef-928a-8574f26a3fa4'
  ) THEN
    RAISE EXCEPTION 'false story event remains';
  END IF;

  SELECT count(*) INTO n
    FROM memory_items
   WHERE id IN (
     '8adddf35-75ac-42e6-8ba6-45250eba7099',
     '7abf826c-546f-44da-8d55-a34d161db505'
   );
  IF n <> 0 THEN
    RAISE EXCEPTION 'false memories remain (%)', n;
  END IF;

  SELECT count(*) INTO n
    FROM story_events
   WHERE id IN (
     '4e04064e-4be7-48fb-b19a-92b57889b615',
     '0b487908-77f2-4f0b-808d-2da01a8824d2'
   )
     AND character_id = '8b491064-97af-43b1-9124-c89977406120'
     AND date = '2026-08-30';
  IF n <> 2 THEN
    RAISE EXCEPTION 'valid stage events changed (% remain)', n;
  END IF;

  SELECT count(*) INTO n
    FROM schedule_activities sa
    JOIN daily_schedules ds ON ds.id = sa.schedule_id
   WHERE sa.id = 'cc5a2014-e13b-4d5f-8722-1d739f0d824f'
     AND ds.character_id = '8b491064-97af-43b1-9124-c89977406120'
     AND sa.memorialized IS FALSE
     AND sa.commitment_key = 'REVIEW-MEET-20260830'
     AND sa.is_first_meeting IS TRUE;
  IF n <> 1 THEN
    RAISE EXCEPTION 'first-meeting schedule changed unexpectedly (%)', n;
  END IF;
END
$postcheck$;

SELECT 'FIRST_MEETING_REPAIR_COMMITTED' AS result;
COMMIT;
