"""Prepare explicitly approved synthetic fixtures; never prints passwords or secrets."""

import json
import secrets
import sys
import uuid
from pathlib import Path

import bcrypt

if "--approved" not in sys.argv:
    raise SystemExit("Requires explicit user approval for temporary Auth test accounts")
folder = Path(".local")
folder.mkdir(exist_ok=True)
path = folder / "account-test.json"
if path.exists():
    raise SystemExit("Existing temporary fixtures need cleanup before preparing another run")
run = str(uuid.uuid4())
accounts = []
sql = ["begin;"]
for label in ["A", "B"]:
    user_id, cert_id = str(uuid.uuid4()), str(uuid.uuid4())
    email = f"certvault-{user_id}@example.test"
    password = secrets.token_urlsafe(32)
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    accounts.append(
        {"id": user_id, "certificate_id": cert_id, "email": email, "password": password}
    )
    sql.append(f"""insert into auth.users(instance_id,id,aud,role,email,encrypted_password,email_confirmed_at,
      raw_app_meta_data,raw_user_meta_data,created_at,updated_at,confirmation_token,recovery_token,email_change_token_new,email_change)
      values ('00000000-0000-0000-0000-000000000000','{user_id}','authenticated','authenticated','{email}','{hashed}',now(),
      '{{"provider":"email","providers":["email"]}}','{{"certvault_test_run":"{run}","display_name":"Synthetic learner {label}"}}',now(),now(),'','','','');
      insert into auth.identities(user_id,provider_id,identity_data,provider,created_at,updated_at)
      values ('{user_id}','{user_id}','{{"sub":"{user_id}","email":"{email}","email_verified":true}}','email',now(),now());
      insert into public.certificates(id,owner_id,title,issuer,source)
      values ('{cert_id}','{user_id}','Synthetic hosted credential {label}','Integration fixture','certvault-test:{run}');""")
sql.append("commit;")
path.write_text(json.dumps({"run": run, "accounts": accounts}), encoding="utf-8")
(folder / "account-test-seed.sql").write_text("\n".join(sql), encoding="utf-8")
ids = ",".join("'" + a["id"] + "'" for a in accounts)
(folder / "account-test-cleanup.sql").write_text(
    f"begin; delete from auth.users where id in ({ids}) and raw_user_meta_data->>'certvault_test_run'='{run}'; select count(*) as remaining_temporary_accounts from auth.users where id in ({ids}); commit;",
    encoding="utf-8",
)
print("Prepared two approved synthetic accounts; credentials kept in ignored local files")
