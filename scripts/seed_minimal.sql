\set ON_ERROR_STOP on

BEGIN;

TRUNCATE TABLE records,
user_device_access,
devices,
marks,
places,
cities,
procedures,
protocols,
users,
app_settings RESTART IDENTITY CASCADE;

INSERT INTO
    app_settings (
        id,
        name,
        description,
        host,
        recordings_dir,
        output_format,
        scan_start_in
    )
VALUES (
        1,
        'Projeto SurgWaze',
        'Streaming Medico',
        'http://192.168.10.19:3000/surgwaze',
        '/recordings',
        'mkv',
        60
    );

INSERT INTO
    users (
        id,
        full_name,
        username,
        password,
        is_superuser,
        is_active
    )
VALUES (
        1,
        'Manager Agent',
        'admin',
        '$2b$12$E2f6pfs9R.Uy7a2RzMo8B.UExK.FAWvuR0dwVW.oAo7syZF9YI82m',
        TRUE,
        TRUE
    ),
    (
        2,
        'Dra. Base',
        'dra',
        '$2b$12$E2f6pfs9R.Uy7a2RzMo8B.UExK.FAWvuR0dwVW.oAo7syZF9YI82m',
        FALSE,
        TRUE
    ),
    (
        3,
        'Dr. Tester',
        'user',
        '$2b$12$E2f6pfs9R.Uy7a2RzMo8B.UExK.FAWvuR0dwVW.oAo7syZF9YI82m',
        FALSE,
        TRUE
    );

INSERT INTO
    cities (id, name, uf, is_active)
VALUES (1, 'Cunha Porã', 'SC', TRUE),
    (2, 'Campinas', 'SP', TRUE);

INSERT INTO
    places (
        id,
        name,
        description,
        city_id,
        is_active
    )
VALUES (
        1,
        'Hospital',
        'Local principal',
        1,
        TRUE
    ),
    (
        2,
        'Santa Casa',
        'Local Campinas',
        2,
        TRUE
    );

INSERT INTO
    protocols (id, name, port, is_active)
VALUES (1, 'srt', 9000, TRUE),
    (2, 'rtmp', 8554, TRUE);

INSERT INTO
    marks (id, name, is_active)
VALUES (1, 'ZowieTek', TRUE),
    (2, 'NEOiD', TRUE);

INSERT INTO
    procedures (
        id,
        name,
        description,
        is_active
    )
VALUES (
        1,
        'Bariatrica',
        'Cirurgia bariatrica',
        TRUE
    ),
    (
        2,
        'Hernia',
        'Cirurgia de hernia',
        TRUE
    ),
    (
        3,
        'Coracao',
        'Cirurgia cardiaca',
        TRUE
    );

INSERT INTO
    devices (
        id,
        model,
        sn,
        key,
        mark_id,
        protocol_id,
        place_id,
        is_active,
        status
    )
VALUES (
        1,
        'ZowieREC-131',
        '29252',
        UPPER(
            SUBSTRING(MD5 ('1' || '29252') FOR 12)
        ),
        1,
        1,
        1,
        TRUE,
        'Offline'
    ),
    (
        2,
        'EDeN',
        'iD25250431536',
        UPPER(
            SUBSTRING(
                MD5 ('2' || 'iD25250431536') FOR 12
            )
        ),
        2,
        2,
        2,
        TRUE,
        'Offline'
    );

SELECT setval (
        pg_get_serial_sequence ('app_settings', 'id'), COALESCE(
            (
                SELECT MAX(id)
                FROM app_settings
            ), 1
        ), TRUE
    );

SELECT setval (
        pg_get_serial_sequence ('users', 'id'), COALESCE(
            (
                SELECT MAX(id)
                FROM users
            ), 1
        ), TRUE
    );

SELECT setval (
        pg_get_serial_sequence ('cities', 'id'), COALESCE(
            (
                SELECT MAX(id)
                FROM cities
            ), 1
        ), TRUE
    );

SELECT setval (
        pg_get_serial_sequence ('places', 'id'), COALESCE(
            (
                SELECT MAX(id)
                FROM places
            ), 1
        ), TRUE
    );

SELECT setval (
        pg_get_serial_sequence ('protocols', 'id'), COALESCE(
            (
                SELECT MAX(id)
                FROM protocols
            ), 1
        ), TRUE
    );

SELECT setval (
        pg_get_serial_sequence ('marks', 'id'), COALESCE(
            (
                SELECT MAX(id)
                FROM marks
            ), 1
        ), TRUE
    );

SELECT setval (
        pg_get_serial_sequence ('procedures', 'id'), COALESCE(
            (
                SELECT MAX(id)
                FROM procedures
            ), 1
        ), TRUE
    );

SELECT setval (
        pg_get_serial_sequence ('devices', 'id'), COALESCE(
            (
                SELECT MAX(id)
                FROM devices
            ), 1
        ), TRUE
    );

COMMIT;