CREATE OR REPLACE VIEW show_slot_attendance_dashboard_base AS
SELECT
    business_unit,
    city_label,
    show_id,
    show_name,
    seance_start_msk,
    seance_date,
    slot_time,
    TO_CHAR(slot_time, 'HH24:MI') AS slot_label,
    EXTRACT(HOUR FROM slot_time)::int * 60 + EXTRACT(MINUTE FROM slot_time)::int AS slot_order,
    iso_weekday,
    weekday_label,
    CASE iso_weekday
        WHEN 1 THEN '1/пн'
        WHEN 2 THEN '2/вт'
        WHEN 3 THEN '3/ср'
        WHEN 4 THEN '4/чт'
        WHEN 5 THEN '5/пт'
        WHEN 6 THEN '6/сб'
        WHEN 7 THEN '7/вск'
    END AS weekday_column_label,
    venue_title,
    venue_city,
    hall_title,
    CASE
        WHEN is_cancelled THEN 0
        ELSE guests_count
    END AS guests_count,
    capacity_tickets,
    tickets_cert,
    tickets_invite,
    is_cancelled,
    CASE
        WHEN capacity_tickets IS NULL OR capacity_tickets = 0 THEN NULL
        ELSE (
            CASE
                WHEN is_cancelled THEN 0
                ELSE guests_count
            END
        )::numeric / capacity_tickets::numeric
    END AS seance_attendance_ratio
FROM erp_show_slot_attendance_snapshot
WHERE COALESCE(show_name, '') <> ''
  AND seance_date >= DATE '2026-01-01'
  AND capacity_tickets IS NOT NULL
  AND capacity_tickets > 0;
