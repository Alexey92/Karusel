# Скрипт сброса всех ID на облаке (сохранить как reset_cloud_ids.sh)
psql -d karusel <<EOF
DELETE FROM events;
DELETE FROM machines;
DELETE FROM jackpot_config;
DELETE FROM locations;
ALTER SEQUENCE locations_id_seq RESTART WITH 1;
ALTER SEQUENCE machines_id_seq RESTART WITH 1;
ALTER SEQUENCE events_id_seq RESTART WITH 1;
ALTER SEQUENCE jackpot_config_id_seq RESTART WITH 1;
EOF