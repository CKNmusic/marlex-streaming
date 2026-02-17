import asyncio
import logging
from datetime import datetime

from app.db.session import SessionLocal
from app.core import security
from app.models.user import User
from app.models.device import Device
from app.models.mark import Mark
from app.models.place import Place
from app.models.city import City
from app.models.procedure import Procedure
from app.models.record import Record
from app.models.protocol import Protocol
from app.models.app_setting import AppSetting
from app.models.user_device_access import UserDeviceAccess  # noqa: F401
from sqlalchemy.future import select
from sqlalchemy import text
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def align_sequence(db, table_name: str, sequence_name: str) -> None:
    await db.execute(
        text(
            f"SELECT setval('{sequence_name}', "
            f"COALESCE((SELECT MAX(id) FROM {table_name}), 0) + 1, false)"
        )
    )

async def init_db() -> None:
    async with SessionLocal() as db:
        # 1.1 Create Default Protocols
        protocols_to_create = [
            {"protocol": "srt", "port": 9000},
            {"protocol": "rtmp", "port": 8554},
        ]
        created_protocols: dict[str, Protocol] = {}
        for prot_data in protocols_to_create:
            res_prot = await db.execute(select(Protocol).where(Protocol.protocol == prot_data["protocol"]))
            protocol = res_prot.scalars().first()
            if not protocol:
                protocol = Protocol(protocol=prot_data["protocol"], port=prot_data["port"])
                db.add(protocol)
                logger.info(f"Protocol '{prot_data['protocol']}' created")
            elif protocol.port != prot_data["port"]:
                protocol.port = prot_data["port"]
                db.add(protocol)
                logger.info(f"Protocol '{prot_data['protocol']}' updated")
            created_protocols[prot_data["protocol"]] = protocol

        # 1.1 Create/Update App Settings
        res_app = await db.execute(select(AppSetting).order_by(AppSetting.id).limit(1))
        app_setting = res_app.scalars().first()
        if not app_setting:
            app_setting = AppSetting(
                id=1,
                name="Projeto SurgWaze",
                description="Streaming Médico",
                host=f"http://{settings.APP_HOST}:3000/{settings.APP_NAME}",
                recordings_dir="/recordings",
                output_format="mkv",
                scan_start_in=60,
            )
            db.add(app_setting)
            logger.info("App settings created")
        else:
            app_setting.name = "Projeto SurgWaze"
            app_setting.description = "Streaming Médico"
            app_setting.host = f"http://{settings.APP_HOST}:3000/{settings.APP_NAME}"
            app_setting.recordings_dir = "/recordings"
            app_setting.output_format = "mkv"
            app_setting.scan_start_in = 60
            db.add(app_setting)
            logger.info("App settings updated")

        # 2. Create/Update Users
        users_to_create = [
            {"username": "admin", "full_name": "Manager Agent", "password": "123", "is_superuser": True, "is_active": True},
            {"username": "user", "full_name": "Dr. Tester", "password": "123", "is_superuser": False, "is_active": True},
            {"username": "dra", "full_name": "Dra. Base", "password": "123", "is_superuser": False, "is_active": True},
            {"username": "user1", "full_name": "User Inativo 01", "password": "123", "is_superuser": False, "is_active": False},
            {"username": "user2", "full_name": "User Inativo 02", "password": "123", "is_superuser": False, "is_active": True},
        ]
        created_users = {}
        for u_data in users_to_create:
            res_u = await db.execute(select(User).where(User.username == u_data["username"]))
            user = res_u.scalars().first()
            if not user:
                user = User(
                    username=u_data["username"],
                    full_name=u_data["full_name"],
                    password=security.get_password_hash(u_data["password"]),
                    is_superuser=u_data["is_superuser"],
                    is_active=u_data["is_active"],
                )
                db.add(user)
                logger.info(f"User '{u_data['username']}' created")
            else:
                user.full_name = u_data["full_name"]
                user.password = security.get_password_hash(u_data["password"])
                user.is_superuser = u_data["is_superuser"]
                user.is_active = u_data["is_active"]
                db.add(user)
                logger.info(f"User '{u_data['username']}' updated")
            created_users[u_data["username"]] = user

        # 3. Create Default Cities
        cities_to_create = [
            {"id": 1, "name": "São Paulo", "uf": "SP"},
            {"id": 2, "name": "Campinas", "uf": "SP"},
            {"id": 3, "name": "Curitiba", "uf": "PR"},
            {"id": 4, "name": "Cunha Porã", "uf": "SC"},
        ]
        created_cities = {}
        for city_data in cities_to_create:
            res_city = await db.execute(select(City).where(City.id == city_data["id"]))
            city = res_city.scalars().first()
            if not city:
                city = City(**city_data)
                db.add(city)
                logger.info(f"City '{city_data['name']}' created")
            else:
                city.name = city_data["name"]
                city.uf = city_data["uf"]
                db.add(city)
                logger.info(f"City '{city_data['name']}' updated")
            created_cities[city_data["id"]] = city

        # 4. Create Default Places
        places_to_create = [
            {"id": 1, "name": "Centro Cirúrgico", "description": "Sala principal", "city_id": 1},
            {"id": 2, "name": "Ambulatório", "description": "Sala ambulatorial", "city_id": 2},
            {"id": 3, "name": "UTI", "description": "Unidade intensiva", "city_id": 3},
            {"id": 4, "name": "Santa Casa", "description": "Centro de gravação", "city_id": 4},
        ]
        created_places = {}
        for loc_data in places_to_create:
            res_loc = await db.execute(select(Place).where(Place.id == loc_data["id"]))
            place = res_loc.scalars().first()
            if not place:
                place = Place(**loc_data)
                db.add(place)
                logger.info(f"Place '{loc_data['name']}' created")
            else:
                place.name = loc_data["name"]
                place.description = loc_data["description"]
                place.city_id = loc_data["city_id"]
                db.add(place)
                logger.info(f"Place '{loc_data['name']}' updated")
            created_places[loc_data["id"]] = place

        # 5. Create default marks
        marks_to_create = ["ZowieTek", "NEOiD"]
        created_marks: dict[str, Mark] = {}
        for mark_name in marks_to_create:
            res_mark = await db.execute(select(Mark).where(Mark.name == mark_name))
            mark = res_mark.scalars().first()
            if not mark:
                mark = Mark(name=mark_name, is_active=True)
                db.add(mark)
                logger.info(f"Mark '{mark_name}' created")
            created_marks[mark_name.lower()] = mark

        # 6. Create Default Devices (strict baseline: only 2 devices)
        devices_to_create = [
            {"mark": "ZowieTek", "model": "ZowieREC-131", "sn": "29252", "place_id": 1, "protocol": "srt", "is_active": True},
            {"mark": "NEOiD", "model": "EDeN", "sn": "iD25250431536", "place_id": 2, "protocol": "rtmp", "is_active": True},
        ]
        created_devices = {}
        target_device_keys: set[tuple[str, int]] = set()
        await db.flush()
        for dev_data in devices_to_create:
            target_mark = created_marks.get(str(dev_data["mark"]).lower())
            if target_mark is None:
                logger.warning(f"Device '{dev_data['mark']} {dev_data['model']}' skipped: mark '{dev_data['mark']}' not found")
                continue
            target_device_keys.add((dev_data["sn"], int(target_mark.id)))
            res_dev = await db.execute(
                select(Device).where(
                    Device.sn == dev_data["sn"],
                    Device.mark_id == target_mark.id,
                )
            )
            device = res_dev.scalars().first()
            target_protocol = created_protocols.get(str(dev_data["protocol"]).lower())
            if target_protocol is None:
                logger.warning(f"Device '{dev_data['mark']} {dev_data['model']}' skipped: protocol '{dev_data['protocol']}' not found")
                continue
            if not device:
                device = Device(
                    model=dev_data["model"],
                    sn=dev_data["sn"],
                    mark_id=target_mark.id,
                    place_id=dev_data["place_id"],
                    protocol_id=target_protocol.id,
                    is_active=dev_data["is_active"],
                )
                db.add(device)
                await db.flush() # Get ID
                device.generate_key()
                logger.info(f"Device '{dev_data['mark']} {dev_data['model']}' created with ID {device.id} and Key {device.key}")
            else:
                device.model = dev_data["model"]
                device.mark_id = target_mark.id
                device.place_id = dev_data["place_id"]
                device.protocol_id = target_protocol.id
                device.is_active = dev_data["is_active"]
                if not device.key:
                    await db.flush()
                    device.generate_key()
                db.add(device)
                logger.info(f"Device '{dev_data['mark']} {dev_data['model']}' updated")
            created_devices[dev_data["sn"]] = device

        # Keep baseline deterministic when this script is executed on an existing DB.
        all_devices_res = await db.execute(select(Device))
        for existing_device in all_devices_res.scalars().all():
            if (existing_device.sn, int(existing_device.mark_id)) in target_device_keys:
                continue
            await db.delete(existing_device)
            logger.info(
                "Device pruned from baseline: sn=%s mark_id=%s",
                existing_device.sn,
                existing_device.mark_id,
            )

        allowed_mark_names = {"zowietek", "neoid"}
        all_marks_res = await db.execute(select(Mark))
        for existing_mark in all_marks_res.scalars().all():
            if str(existing_mark.name or "").strip().lower() in allowed_mark_names:
                continue
            await db.delete(existing_mark)
            logger.info("Mark pruned from baseline: %s", existing_mark.name)

        # 7. Create Default Procedures
        procedures_to_create = [
            {"name": "Bariatrica", "description": "Cirurgia bariátrica", "is_active": True},
            {"name": "Hernia", "description": "Cirurgia de hérnia", "is_active": True},
            {"name": "Coração", "description": "Cirurgia cardíaca", "is_active": True}
        ]
        created_procs = {}
        for proc_data in procedures_to_create:
            res_proc = await db.execute(select(Procedure).where(Procedure.name == proc_data["name"]))
            proc = res_proc.scalars().first()
            if not proc:
                proc = Procedure(
                    name=proc_data["name"],
                    description=proc_data["description"],
                    is_active=proc_data["is_active"]
                )
                db.add(proc)
                logger.info(f"Procedure '{proc_data['name']}' created")
            else:
                proc.description = proc_data["description"]
                proc.is_active = proc_data["is_active"]
                db.add(proc)
                logger.info(f"Procedure '{proc_data['name']}' updated")
            created_procs[proc_data["name"]] = proc
            
        await db.flush()
        
        # 8. Create Initial Record Streams
        res_rec = await db.execute(select(Record).where(Record.id == 1))
        if not res_rec.scalars().first():
            admin_user = created_users.get("admin")
            base_device = created_devices.get("29252")
            base_procedure = created_procs.get("Bariatrica")

            if not admin_user or not base_device or not base_procedure:
                logger.warning("Initial Record skipped: missing FK references")
                await db.commit()
                return

            new_record = Record(
                id=1,
                device_id=base_device.id,
                procedure_id=base_procedure.id,
                owner_id=admin_user.id,
                place_id=base_device.place_id,
                start_time=datetime(2022, 1, 1, 12, 0, 0),
            )
            db.add(new_record)
            logger.info("Initial Record created")

        await db.flush()

        # Keep PostgreSQL sequences aligned after fixed-ID seed inserts.
        await align_sequence(db, "users", "users_id_seq")
        await align_sequence(db, "devices", "devices_id_seq")
        await align_sequence(db, "marks", "marks_id_seq")
        await align_sequence(db, "protocols", "protocols_id_seq")
        await align_sequence(db, "app_settings", "app_settings_id_seq")
        await align_sequence(db, "procedures", "procedures_id_seq")
        await align_sequence(db, "records", "records_id_seq")
        await align_sequence(db, "cities", "cities_id_seq")
        await align_sequence(db, "places", "places_id_seq")

        await db.commit()

if __name__ == "__main__":
    asyncio.run(init_db())
