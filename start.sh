#!/usr/bin/env sh
set -eu

APP_DIR=${APP_DIR:-/app}
REQ_FILE=${REQ_FILE:-$APP_DIR/requirements.txt}
REQ_HASH_FILE=${REQ_HASH_FILE:-$APP_DIR/.requirements.sha256}

echo "[start] Python: $(python --version)"
echo "[start] App dir: $APP_DIR"
echo "[start] Using requirements: $REQ_FILE"

DB_HOST="${DB_HOST}"
DB_PORT="${DB_PORT}"
PG_USER="${PG_USER}"
PG_DB="${PG_DB}"
export PGPASSWORD="${PG_PASSWORD}"

echo "[start] Waiting for Postgres at ${DB_HOST}:${DB_PORT} (db=${PG_DB} user=${PG_USER})..."
until PGPASSWORD="$PG_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$PG_USER" -d "$PG_DB" -c '\q' >/dev/null 2>&1; do
  >&2 echo "[start] Postgres not ready yet — sleeping"
  sleep 2
done
echo "[start] Postgres is up — continuing"

if [ -f "$REQ_FILE" ]; then
  NEW_HASH=$(sha256sum "$REQ_FILE" | awk '{print $1}')
  OLD_HASH=""
  [ -f "$REQ_HASH_FILE" ] && OLD_HASH=$(cat "$REQ_HASH_FILE")

  if [ "$NEW_HASH" != "$OLD_HASH" ]; then
    echo "[start] Requirements changed → installing…"
    python -m pip install --upgrade pip
    python -m pip install --no-cache-dir -r "$REQ_FILE"
    echo "$NEW_HASH" > "$REQ_HASH_FILE"
  else
    echo "[start] Requirements unchanged → skipping install."
  fi
else
  echo "[start] No requirements file found at $REQ_FILE (skipping)"
fi

cd "$APP_DIR"

echo "[start] Ensuring migrations exist for all apps..."
for app in accounts payroll attendance reports; do
  if [ -d "$APP_DIR/apps/$app" ]; then
    MIGRATION_DIR="$APP_DIR/apps/$app/migrations"
    if [ ! -d "$MIGRATION_DIR" ] || [ -z "$(find "$MIGRATION_DIR" -maxdepth 1 -name '00*.py' 2>/dev/null)" ]; then
      echo "[start] No migrations found for $app - creating..."
      python manage.py makemigrations "$app" --noinput
    else
      echo "[start] Migrations exist for $app"
      python manage.py makemigrations "$app" --noinput --dry-run > /dev/null 2>&1 || \
      python manage.py makemigrations "$app" --noinput
    fi
  fi
done

echo "[start] Checking database state..."
TABLE_COUNT=0
if TABLE_COUNT=$(PGPASSWORD="$PG_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$PG_USER" -d "$PG_DB" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null | xargs); then
  echo "[start] Found $TABLE_COUNT tables in database"
else
  echo "[start] Could not query database, assuming empty"
  TABLE_COUNT=0
fi

[ "$TABLE_COUNT" -eq 0 ] && echo "[start] Empty database detected" && echo "[start] Running full migration setup..."

echo "[start] Applying migrations..."
python manage.py migrate --noinput

echo "[start] Verifying migration status..."
UNAPPLIED="$(python manage.py showmigrations --plan 2>/dev/null | awk '/^\[ \]/{c++} END{print c+0}')"
echo "${UNAPPLIED:-0}" | grep -Eq '^[0-9]+$' || UNAPPLIED=0
if [ "$UNAPPLIED" -gt 0 ]; then
  echo "[start] Found $UNAPPLIED unapplied migrations - applying..."
  python manage.py migrate --noinput
else
  echo "[start] All migrations applied successfully"
fi

count_users () {
  python manage.py shell -c "from django.contrib.auth import get_user_model as g; print(g().objects.count())"
}

echo ""
echo "=========================================="
echo "FIXTURE LOADING"
echo "=========================================="

# STEP 1: Load users fixture ONLY if no users exist
echo "[seed] Checking for user data..."
USER_COUNT="$(count_users 2>/dev/null | tr -d '\r' | tail -n1)"
echo "$USER_COUNT" | grep -Eq '^[0-9]+$' || USER_COUNT=0
echo "[seed] Found $USER_COUNT users in database"

if [ "${USER_COUNT:-0}" -eq 0 ]; then
  echo "[seed] No users found - loading users fixture..."
  
  if python manage.py loaddata apps/accounts/fixtures/user.json 2>/dev/null; then
    echo "[seed]   Users fixture loaded successfully"
    
    echo "[seed] Setting password for superuser (pk=1)..."
    python manage.py shell <<'PY'
from django.contrib.auth import get_user_model as g
try:
    u = g().objects.get(pk=1)
    u.set_password("Admin123!")
    u.is_staff = True
    u.is_superuser = True
    u.save()
    print("  Superuser ready (username: {}, password: Admin123!)".format(u.username))
except g().DoesNotExist:
    print("  User with pk=1 not found - skipping superuser setup")
PY
    
    USER_COUNT="$(count_users 2>/dev/null | tr -d '\r' | tail -n1)"
    echo "$USER_COUNT" | grep -Eq '^[0-9]+$' || USER_COUNT=0
    echo "[seed] Total users in DB: $USER_COUNT"
  else
    echo "[seed]   No user fixture found at apps/accounts/fixtures/user.json"
  fi
else
  echo "[seed]   Users already present ($USER_COUNT) - skipping user fixture"
fi

# STEP 2: Load other fixtures (INDEPENDENT of user count check)
echo ""
echo "[seed] =========================================="
echo "[seed] Loading additional fixtures..."
echo "[seed] =========================================="

FIXTURE_ORDER="payrollperiod compensation bonus attendance_record monthly_attendance_summary vacation_balance payslips"

for fixture in $FIXTURE_ORDER; do
  echo "[seed] Attempting to load: $fixture"
  
  FOUND=false
  
  # Try to find fixture in app-specific directories
  for app_dir in apps/payroll/fixtures apps/attendance/fixtures apps/reports/fixtures; do
    FIXTURE_PATH="${app_dir}/${fixture}.json"
    
    if [ -f "$FIXTURE_PATH" ]; then
      echo "[seed]   → Found at $FIXTURE_PATH"
      
      if python manage.py loaddata "$FIXTURE_PATH" 2>/dev/null; then
        echo "[seed]     Successfully loaded $fixture"
        FOUND=true
        break
      else
        echo "[seed]     Failed to load $fixture from $FIXTURE_PATH"
      fi
    fi
  done
  
  # If not found in app directories, try global fixtures directory
  if [ "$FOUND" = false ]; then
    GLOBAL_FIXTURE="$APP_DIR/fixtures/${fixture}.json"
    
    if [ -f "$GLOBAL_FIXTURE" ]; then
      echo "[seed]   → Found at $GLOBAL_FIXTURE"
      
      if python manage.py loaddata "$GLOBAL_FIXTURE" 2>/dev/null; then
        echo "[seed]     Successfully loaded $fixture"
        FOUND=true
      else
        echo "[seed]     Failed to load $fixture from $GLOBAL_FIXTURE"
      fi
    fi
  fi
  
  # If still not found, try Django's default fixture search
  if [ "$FOUND" = false ]; then
    echo "[seed]   → Trying Django default fixture locations..."
    
    if python manage.py loaddata "$fixture" 2>/dev/null; then
      echo "[seed]     Loaded $fixture from default location"
      FOUND=true
    fi
  fi
  
  # Report if fixture was not found anywhere
  if [ "$FOUND" = false ]; then
    echo "[seed]     Fixture '$fixture.json' not found - skipping"
  fi
  
  echo ""
done

echo "[seed] =========================================="
echo "[seed] Fixture loading complete!"
echo "[seed] =========================================="

echo ""
echo "=========================================="
echo "  Startup complete!"
echo "=========================================="
echo ""
echo "[start] Starting Django development server on 0.0.0.0:8000"
exec python manage.py runserver 0.0.0.0:8000