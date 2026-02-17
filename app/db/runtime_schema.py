from sqlalchemy import text

from app.db.session import engine


async def ensure_core_schema_migrations() -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                DO $$
                DECLARE
                    has_legacy_name BOOLEAN;
                    needs_mark_backfill BOOLEAN;
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'marks'
                    ) THEN
                        CREATE TABLE marks (
                            id SERIAL PRIMARY KEY,
                            name VARCHAR(120) NOT NULL,
                            is_active BOOLEAN NOT NULL DEFAULT TRUE,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                        );
                    END IF;
                    CREATE INDEX IF NOT EXISTS ix_marks_name ON marks (name);

                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'marks'
                    ) THEN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_constraint
                            WHERE conname = 'uq_marks_name'
                        ) THEN
                            ALTER TABLE marks ADD CONSTRAINT uq_marks_name UNIQUE (name);
                        END IF;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'devices'
                    ) THEN
                        RETURN;
                    END IF;

                    has_legacy_name := EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'devices'
                          AND column_name = 'name'
                    );

                    IF has_legacy_name
                    AND NOT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'devices'
                          AND column_name = 'model'
                    ) THEN
                        ALTER TABLE devices RENAME COLUMN name TO model;
                        has_legacy_name := FALSE;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'devices'
                          AND column_name = 'model'
                    ) THEN
                        ALTER TABLE devices ADD COLUMN model VARCHAR(255);
                    END IF;

                    IF has_legacy_name THEN
                        UPDATE devices
                        SET model = COALESCE(NULLIF(BTRIM(model), ''), BTRIM(name))
                        WHERE model IS NULL OR BTRIM(model) = '';
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'devices'
                          AND column_name = 'mark_id'
                    ) THEN
                        ALTER TABLE devices ADD COLUMN mark_id INTEGER;
                    END IF;

                    needs_mark_backfill := EXISTS (
                        SELECT 1 FROM devices WHERE mark_id IS NULL
                    );

                    IF needs_mark_backfill THEN
                        IF has_legacy_name THEN
                            INSERT INTO marks (name, is_active)
                            SELECT DISTINCT split_part(BTRIM(name), ' ', 1), TRUE
                            FROM devices
                            WHERE BTRIM(COALESCE(name, '')) <> ''
                              AND NOT EXISTS (
                                  SELECT 1
                                  FROM marks m
                                  WHERE lower(m.name) = lower(split_part(BTRIM(name), ' ', 1))
                              );

                            UPDATE devices d
                            SET mark_id = m.id
                            FROM marks m
                            WHERE d.mark_id IS NULL
                              AND lower(m.name) = lower(split_part(BTRIM(d.name), ' ', 1));

                            UPDATE devices
                            SET model = CASE
                                WHEN position(' ' in BTRIM(name)) > 0
                                    THEN BTRIM(substring(BTRIM(name) from position(' ' in BTRIM(name)) + 1))
                                ELSE BTRIM(name)
                            END;
                        ELSE
                            INSERT INTO marks (name, is_active)
                            SELECT DISTINCT split_part(BTRIM(model), ' ', 1), TRUE
                            FROM devices
                            WHERE BTRIM(COALESCE(model, '')) <> ''
                              AND NOT EXISTS (
                                  SELECT 1
                                  FROM marks m
                                  WHERE lower(m.name) = lower(split_part(BTRIM(model), ' ', 1))
                              );

                            UPDATE devices d
                            SET mark_id = m.id
                            FROM marks m
                            WHERE d.mark_id IS NULL
                              AND lower(m.name) = lower(split_part(BTRIM(d.model), ' ', 1));
                        END IF;

                        INSERT INTO marks (name, is_active)
                        SELECT 'Generic', TRUE
                        WHERE NOT EXISTS (
                            SELECT 1 FROM marks WHERE lower(name) = 'generic'
                        );

                        UPDATE devices d
                        SET mark_id = m.id
                        FROM marks m
                        WHERE d.mark_id IS NULL
                          AND lower(m.name) = 'generic';
                    END IF;

                    ALTER TABLE devices
                        ALTER COLUMN model SET NOT NULL,
                        ALTER COLUMN mark_id SET NOT NULL;

                    IF has_legacy_name THEN
                        ALTER TABLE devices DROP COLUMN name;
                    END IF;

                    CREATE INDEX IF NOT EXISTS ix_devices_model ON devices (model);
                    CREATE INDEX IF NOT EXISTS ix_devices_mark_id ON devices (mark_id);
                    IF EXISTS (
                        SELECT 1
                        FROM pg_indexes
                        WHERE schemaname = 'public'
                          AND indexname = 'ix_devices_name'
                    ) THEN
                        DROP INDEX ix_devices_name;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'fk_devices_mark_id'
                    ) THEN
                        ALTER TABLE devices
                            ADD CONSTRAINT fk_devices_mark_id
                            FOREIGN KEY (mark_id)
                            REFERENCES marks (id)
                            ON DELETE RESTRICT;
                    END IF;

                    IF EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'uq_devices_sn'
                    ) THEN
                        ALTER TABLE devices DROP CONSTRAINT uq_devices_sn;
                    END IF;
                    IF EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'devices_sn_key'
                    ) THEN
                        ALTER TABLE devices DROP CONSTRAINT devices_sn_key;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'uq_devices_sn_mark'
                    ) THEN
                        ALTER TABLE devices
                            ADD CONSTRAINT uq_devices_sn_mark UNIQUE (sn, mark_id);
                    END IF;
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'protocols'
                    ) THEN
                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'protocols'
                              AND column_name = 'protocol'
                        )
                        AND NOT EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'protocols'
                              AND column_name = 'name'
                        ) THEN
                            ALTER TABLE protocols RENAME COLUMN protocol TO name;
                        END IF;
                    END IF;
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_type
                        WHERE typname = 'device_status'
                    ) THEN
                        CREATE TYPE device_status AS ENUM ('Offline', 'Connecting', 'Online', 'Starting', 'Recording', 'Stopping');
                    END IF;
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM pg_type
                        WHERE typname = 'device_status'
                    ) THEN
                        ALTER TYPE device_status ADD VALUE IF NOT EXISTS 'Connecting';
                        ALTER TYPE device_status ADD VALUE IF NOT EXISTS 'Starting';
                        ALTER TYPE device_status ADD VALUE IF NOT EXISTS 'Stopping';
                    END IF;
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'devices'
                    ) THEN
                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'devices'
                              AND column_name = 'connection_status'
                        )
                        AND NOT EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'devices'
                              AND column_name = 'status'
                        ) THEN
                            ALTER TABLE devices RENAME COLUMN connection_status TO status;
                        END IF;
                    END IF;
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'devices'
                    ) AND EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'devices'
                          AND column_name = 'status'
                    ) THEN
                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'devices'
                              AND column_name = 'status'
                              AND udt_name <> 'device_status'
                        ) THEN
                            ALTER TABLE devices ALTER COLUMN status DROP DEFAULT;
                            ALTER TABLE devices
                            ALTER COLUMN status TYPE device_status
                            USING (
                                CASE
                                    WHEN status IS NULL THEN 'Offline'
                                    WHEN lower(status::text) = 'connecting' THEN 'Connecting'
                                    WHEN lower(status::text) = 'online' THEN 'Online'
                                    WHEN lower(status::text) = 'starting' THEN 'Starting'
                                    WHEN lower(status::text) = 'recording' THEN 'Recording'
                                    WHEN lower(status::text) = 'stopping' THEN 'Stopping'
                                    ELSE 'Offline'
                                END
                            )::device_status;
                        END IF;

                        ALTER TABLE devices
                            ALTER COLUMN status SET DEFAULT 'Offline',
                            ALTER COLUMN status SET NOT NULL;

                        IF EXISTS (
                            SELECT 1
                            FROM pg_constraint
                            WHERE conname = 'ck_devices_connection_status'
                        ) THEN
                            ALTER TABLE devices DROP CONSTRAINT ck_devices_connection_status;
                        END IF;

                        IF EXISTS (
                            SELECT 1
                            FROM pg_constraint
                            WHERE conname = 'ck_devices_status'
                        ) THEN
                            ALTER TABLE devices DROP CONSTRAINT ck_devices_status;
                        END IF;

                        IF EXISTS (
                            SELECT 1
                            FROM pg_indexes
                            WHERE schemaname = 'public'
                              AND indexname = 'ix_devices_connection_status'
                        ) THEN
                            DROP INDEX ix_devices_connection_status;
                        END IF;
                        CREATE INDEX IF NOT EXISTS ix_devices_status ON devices (status);
                    END IF;
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'protocols'
                    ) THEN
                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'protocols'
                              AND column_name = 'name'
                        ) THEN
                            INSERT INTO protocols (name, port, is_active)
                            SELECT 'srt', 9000, TRUE
                            WHERE NOT EXISTS (
                                SELECT 1 FROM protocols WHERE lower(name) = 'srt'
                            );

                            INSERT INTO protocols (name, port, is_active)
                            SELECT 'rtmp', 8554, TRUE
                            WHERE NOT EXISTS (
                                SELECT 1 FROM protocols WHERE lower(name) = 'rtmp'
                            );
                        END IF;
                    END IF;
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'devices'
                    ) THEN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'devices'
                              AND column_name = 'protocol_id'
                        ) THEN
                            ALTER TABLE devices ADD COLUMN protocol_id INTEGER;
                        END IF;
                    END IF;
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'devices'
                    ) AND EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'protocols'
                    ) THEN
                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'devices'
                              AND column_name = 'protocol'
                        ) THEN
                            UPDATE devices d
                            SET protocol_id = COALESCE(
                                (
                                    SELECT p.id
                                    FROM protocols p
                                    WHERE lower(p.name) = lower(d.protocol)
                                    ORDER BY p.id
                                    LIMIT 1
                                ),
                                (
                                    SELECT p.id
                                    FROM protocols p
                                    WHERE lower(p.name) = 'srt'
                                    ORDER BY p.id
                                    LIMIT 1
                                ),
                                (
                                    SELECT p.id
                                    FROM protocols p
                                    ORDER BY p.id
                                    LIMIT 1
                                )
                            )
                            WHERE d.protocol_id IS NULL;
                        ELSE
                            UPDATE devices d
                            SET protocol_id = COALESCE(
                                (
                                    SELECT p.id
                                    FROM protocols p
                                    WHERE lower(p.name) = 'srt'
                                    ORDER BY p.id
                                    LIMIT 1
                                ),
                                (
                                    SELECT p.id
                                    FROM protocols p
                                    ORDER BY p.id
                                    LIMIT 1
                                )
                            )
                            WHERE d.protocol_id IS NULL;
                        END IF;
                    END IF;
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'devices'
                    ) THEN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_constraint
                            WHERE conname = 'fk_devices_protocol_id'
                        ) THEN
                            ALTER TABLE devices
                            ADD CONSTRAINT fk_devices_protocol_id
                            FOREIGN KEY (protocol_id)
                            REFERENCES protocols (id)
                            ON DELETE RESTRICT;
                        END IF;
                        CREATE INDEX IF NOT EXISTS ix_devices_protocol_id ON devices (protocol_id);
                    END IF;
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'devices'
                    ) THEN
                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'devices'
                              AND column_name = 'protocol_id'
                        ) THEN
                            IF EXISTS (
                                SELECT 1
                                FROM devices
                                WHERE protocol_id IS NULL
                            ) THEN
                                RAISE EXCEPTION 'devices.protocol_id possui valores nulos apos migracao';
                            END IF;
                            IF EXISTS (
                                SELECT 1
                                FROM information_schema.columns
                                WHERE table_schema = 'public'
                                  AND table_name = 'devices'
                                  AND column_name = 'protocol_id'
                                  AND is_nullable = 'YES'
                            ) THEN
                                ALTER TABLE devices
                                ALTER COLUMN protocol_id SET NOT NULL;
                            END IF;
                        END IF;
                    END IF;
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'devices'
                    ) THEN
                        IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_devices_qr_code_token') THEN
                            ALTER TABLE devices DROP CONSTRAINT uq_devices_qr_code_token;
                        END IF;
                        IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_devices_device_session_id') THEN
                            ALTER TABLE devices DROP CONSTRAINT uq_devices_device_session_id;
                        END IF;
                        IF EXISTS (
                            SELECT 1
                            FROM pg_indexes
                            WHERE schemaname = 'public'
                              AND indexname = 'ix_devices_qr_code_token'
                        ) THEN
                            DROP INDEX ix_devices_qr_code_token;
                        END IF;
                        IF EXISTS (
                            SELECT 1
                            FROM pg_indexes
                            WHERE schemaname = 'public'
                              AND indexname = 'ix_devices_device_session_id'
                        ) THEN
                            DROP INDEX ix_devices_device_session_id;
                        END IF;

                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'devices'
                              AND column_name = 'qr_code_token'
                        ) THEN
                            ALTER TABLE devices DROP COLUMN qr_code_token;
                        END IF;
                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'devices'
                              AND column_name = 'device_session_id'
                        ) THEN
                            ALTER TABLE devices DROP COLUMN device_session_id;
                        END IF;
                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'devices'
                              AND column_name = 'stream_key'
                        ) THEN
                            ALTER TABLE devices DROP COLUMN stream_key;
                        END IF;
                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'devices'
                              AND column_name = 'device_user'
                        ) THEN
                            ALTER TABLE devices DROP COLUMN device_user;
                        END IF;
                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'devices'
                              AND column_name = 'device_password'
                        ) THEN
                            ALTER TABLE devices DROP COLUMN device_password;
                        END IF;
                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'devices'
                              AND column_name = 'protocol'
                        ) THEN
                            ALTER TABLE devices DROP COLUMN protocol;
                        END IF;
                    END IF;
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'protocols'
                    ) THEN
                        IF EXISTS (
                            SELECT 1
                            FROM pg_constraint
                            WHERE conname = 'uq_protocols_protocol'
                        ) AND NOT EXISTS (
                            SELECT 1
                            FROM pg_constraint
                            WHERE conname = 'uq_protocols_name'
                        ) THEN
                            ALTER TABLE protocols
                            RENAME CONSTRAINT uq_protocols_protocol TO uq_protocols_name;
                        END IF;

                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_constraint
                            WHERE conname = 'uq_protocols_name'
                        ) THEN
                            ALTER TABLE protocols
                                ADD CONSTRAINT uq_protocols_name UNIQUE (name);
                        END IF;
                    END IF;
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'app_settings'
                    ) THEN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'app_settings'
                              AND column_name = 'scan_start_in'
                        ) THEN
                            ALTER TABLE app_settings
                                ADD COLUMN scan_start_in INTEGER NOT NULL DEFAULT 60;
                        END IF;

                        UPDATE app_settings
                        SET scan_start_in = 60
                        WHERE scan_start_in IS NULL OR scan_start_in < 5 OR scan_start_in > 600;

                        ALTER TABLE app_settings
                            ALTER COLUMN scan_start_in SET DEFAULT 60,
                            ALTER COLUMN scan_start_in SET NOT NULL;
                    END IF;
                END $$;
                """
            )
        )


async def ensure_invites_table() -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS invites (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(32) NOT NULL UNIQUE,
                    created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    used_by INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
                    used_at TIMESTAMPTZ NULL,
                    expires_at TIMESTAMPTZ NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_invites_code ON invites (code)")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_invites_created_by ON invites (created_by)")
        )


async def ensure_runtime_schema() -> None:
    await ensure_core_schema_migrations()
    await ensure_invites_table()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS user_profile_photos (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                    content_type VARCHAR(64) NOT NULL,
                    image_blob BYTEA NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS user_notifications (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(40) NOT NULL UNIQUE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    record_id INTEGER NULL,
                    record_public_id VARCHAR(32) NULL,
                    notification_type VARCHAR(64) NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    message TEXT NOT NULL,
                    is_read BOOLEAN NOT NULL DEFAULT FALSE,
                    read_at TIMESTAMPTZ NULL,
                    visible_to_user BOOLEAN NOT NULL DEFAULT TRUE,
                    deleted_by_user BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_user_notifications_user_created ON user_notifications (user_id, created_at DESC)")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_user_notifications_user_unread ON user_notifications (user_id, is_read)")
        )
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS user_notification_viewer_states (
                    id SERIAL PRIMARY KEY,
                    notification_id INTEGER NOT NULL REFERENCES user_notifications(id) ON DELETE CASCADE,
                    viewer_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    is_read BOOLEAN NOT NULL DEFAULT FALSE,
                    read_at TIMESTAMPTZ NULL,
                    deleted_by_user BOOLEAN NOT NULL DEFAULT FALSE,
                    deleted_at TIMESTAMPTZ NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    CONSTRAINT uq_user_notification_viewer_state_notification_viewer
                        UNIQUE (notification_id, viewer_user_id)
                )
                """
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_user_notification_viewer_states_viewer "
                "ON user_notification_viewer_states (viewer_user_id, notification_id)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_user_notification_viewer_states_viewer_unread "
                "ON user_notification_viewer_states (viewer_user_id, is_read, deleted_by_user)"
            )
        )
