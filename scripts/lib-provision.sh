#!/usr/bin/env bash
# Shared provisioning steps for install.sh and update.sh.
#
# Sourced, never executed. Expects APP_DIR to be set and the caller to be root.
# Everything here is idempotent so it can run on every update.

SERVICE_USER="dynadash"
# Only referenced to remove it: an earlier version granted the backend sudo.
SUDOERS_FILE="/etc/sudoers.d/dynadash"

# ---------------------------------------------------------------------------
# The unprivileged account the backend runs as
# ---------------------------------------------------------------------------
provision_user() {
    if ! id -u "${SERVICE_USER}" &>/dev/null; then
        useradd --system --no-create-home --shell /usr/sbin/nologin \
                --comment "DynaDash backend" "${SERVICE_USER}"
    fi
}

# ---------------------------------------------------------------------------
# Ownership: the code is root-owned and read-only to the service, which may
# write only its data directory. That boundary is what stops a compromised
# backend from rewriting the helper it invokes through sudo.
# ---------------------------------------------------------------------------
provision_permissions() {
    local backend_dir="${APP_DIR}/backend"
    local data_dir="${backend_dir}/data"
    local helper="${APP_DIR}/scripts/dynadash-admin"

    mkdir -p "${data_dir}"
    chown -R "${SERVICE_USER}:${SERVICE_USER}" "${data_dir}"
    # The Tibber token lives in here, so keep it off limits to other accounts.
    chmod 750 "${data_dir}"

    # config.yaml holds the InfluxDB token: readable by the service, writable
    # only by root.
    if [[ -f "${backend_dir}/config.yaml" ]]; then
        chown "root:${SERVICE_USER}" "${backend_dir}/config.yaml"
        chmod 640 "${backend_dir}/config.yaml"
    fi

    chown root:root "${helper}" "${APP_DIR}/update.sh" "${APP_DIR}/install.sh"
    chmod 755 "${helper}"
    chmod go-w "${APP_DIR}" "${APP_DIR}/scripts" "${APP_DIR}/update.sh" \
               "${APP_DIR}/install.sh"

    # A tree the service can write is a root escalation waiting to happen, since
    # update.sh and the sudo helper both run from it.
    if su -s /bin/sh -c "test -w '${helper}'" "${SERVICE_USER}" 2>/dev/null; then
        echo "WARNING: ${helper} is writable by ${SERVICE_USER} — fix its ownership." >&2
    fi
}

# ---------------------------------------------------------------------------
# Drop the sudo grant an earlier version installed
# ---------------------------------------------------------------------------
# Privileged update steps now go through dynadash-update.path, so the backend
# needs no sudo at all — and without a setuid path it can run under
# NoNewPrivileges. Leaving a stale grant behind would only widen it again.
provision_remove_sudoers() {
    if [[ -f "${SUDOERS_FILE}" ]]; then
        rm -f "${SUDOERS_FILE}"
        echo "  removed the obsolete sudo grant at ${SUDOERS_FILE}"
    fi
}

# ---------------------------------------------------------------------------
# systemd units, rendered from the templates in systemd/
# ---------------------------------------------------------------------------
_render_unit() {
    local template="${APP_DIR}/systemd/$1" target="/etc/systemd/system/$2"
    [[ -f "${template}" ]] || { echo "ERROR: missing ${template}" >&2; return 1; }
    sed -e "s|@APP_DIR@|${APP_DIR}|g" \
        -e "s|@BACKEND_DIR@|${APP_DIR}/backend|g" \
        -e "s|@SERVICE_USER@|${SERVICE_USER}|g" \
        "${template}" > "${target}"
    chmod 644 "${target}"
}

provision_service_unit() {
    _render_unit dynadash-backend.service.in dynadash-backend.service
    _render_unit dynadash-update.service dynadash-update.service
    _render_unit dynadash-update.path dynadash-update.path
    systemctl daemon-reload
    # The path unit has to be running for the dashboard's update button to do
    # anything at all.
    systemctl enable --now dynadash-update.path --quiet
}

# Everything above, in the order they depend on each other.
provision_all() {
    provision_user
    provision_permissions
    provision_remove_sudoers
    provision_service_unit
}
