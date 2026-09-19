#!/usr/bin/env bash
# Shared provisioning steps for install.sh and update.sh.
#
# Sourced, never executed. Expects APP_DIR to be set and the caller to be root.
# Everything here is idempotent so it can run on every update.

SERVICE_USER="dynadash"
SUDOERS_FILE="/etc/sudoers.d/dynadash"
UNIT_FILE="/etc/systemd/system/dynadash-backend.service"

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
# The narrow sudo grant that lets the unprivileged backend run the updater
# ---------------------------------------------------------------------------
provision_sudoers() {
    local helper="${APP_DIR}/scripts/dynadash-admin"
    local tmp
    tmp="$(mktemp)"
    cat > "${tmp}" <<EOF
# Managed by DynaDash install.sh — do not edit by hand.
#
# The backend runs as ${SERVICE_USER} and cannot use git or systemd directly.
# These three actions are the whole of its privilege; each is spelled out in
# full so no other command or argument can be substituted.
${SERVICE_USER} ALL=(root) NOPASSWD: ${helper} fetch
${SERVICE_USER} ALL=(root) NOPASSWD: ${helper} revs
${SERVICE_USER} ALL=(root) NOPASSWD: ${helper} apply
EOF
    # A malformed drop-in breaks sudo for everyone, so never install one blind.
    if ! visudo -c -q -f "${tmp}" &>/dev/null; then
        rm -f "${tmp}"
        echo "ERROR: generated sudoers file is invalid — not installing it." >&2
        return 1
    fi
    install -o root -g root -m 440 "${tmp}" "${SUDOERS_FILE}"
    rm -f "${tmp}"
}

# ---------------------------------------------------------------------------
# The systemd unit, rendered from systemd/dynadash-backend.service.in
# ---------------------------------------------------------------------------
provision_service_unit() {
    local template="${APP_DIR}/systemd/dynadash-backend.service.in"
    [[ -f "${template}" ]] || { echo "ERROR: missing ${template}" >&2; return 1; }
    sed -e "s|@BACKEND_DIR@|${APP_DIR}/backend|g" \
        -e "s|@SERVICE_USER@|${SERVICE_USER}|g" \
        "${template}" > "${UNIT_FILE}"
    chmod 644 "${UNIT_FILE}"
    systemctl daemon-reload
}

# Everything above, in the order they depend on each other.
provision_all() {
    provision_user
    provision_permissions
    provision_sudoers
    provision_service_unit
}
