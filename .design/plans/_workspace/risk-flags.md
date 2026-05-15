# Risk flags — `ubuntu/` source

> **Workspace document.** Captures every flagged pattern. The
> migration plan must address each Critical / High flag before the
> related feature is adopted; Lows can be noted in the per-tool doc.

## No hardcoded secrets, keys, or IPs

Greps for `PRIVATE KEY`, `BEGIN PGP`, `PASSWORD=<literal>`, `API_KEY`,
`SECRET`, `TOKEN`, IPv4 literals, ssh fingerprints returned zero
**actual** values. The only "secret-shaped" hits are:

- `REDIS_PASSWORD=null` / `MAIL_PASSWORD=null` / `PUSHER_APP_SECRET=`
  — these are template placeholders in the `.env` file that
  `laravel:initialize.sh` generates, not real credentials.
- `$mysql_password=$3` / `$mongo_password="$2"` — bash positional
  arg captures, not literal values.

## Critical (must address before any adoption)

| # | Pattern | Files | Why |
|---|---------|-------|-----|
| C1 | `service apparmor stop && teardown && update-rc.d -f apparmor remove` | `install:maria.sh:25-27` | Permanently disables AppArmor system-wide. Security regression with blast radius beyond MariaDB. |
| C2 | `bindIp: 0.0.0.0` written to `/etc/mongod.conf` | `install:mongo.sh:24` | Exposes MongoDB on every interface with no auth gate, then opens UFW 27017. **Network-reachable unauthenticated database.** |
| C3 | MySQL grants `*.*` to `'%'` over network | `install:mysql.sh:23,27` | `GRANT ALL ON *.* TO root@'%' IDENTIFIED BY '$pass'`; also `bind-address = *`. Same pattern as C2 — network-reachable DB. |
| C4 | `apt-key adv --recv-keys` from keyserver.ubuntu.com | `install:maria.sh:40`, `install:mongo.sh:15` | **Deprecated and removed** in Ubuntu 22.04+. Will silently fail. Even on older Ubuntu, keyserver-fetched keys are a weak trust model (no maintainer-pinned fingerprint). |
| C5 | `curl ... \| sudo -E bash -` | `install:node.sh:5` | Classic curl-pipe-bash. No checksum, no signature, network-MITM-vulnerable. NodeSource at least serves over HTTPS, but pinning a release is still better. |

## High

| # | Pattern | Files | Why |
|---|---------|-------|-----|
| H1 | Password on command line — `mysql --password="$pwd" -e "..."` | `install:mysql.sh:21-29`, `install:maria.sh` | Process list leaks the password to every other user via `ps`. Should use `mysql_config_editor` or `MYSQL_PWD` env var. |
| H2 | Marker files at `/home/vagrant/.maria`, `/home/capybara/.mongo` | `install:maria.sh`, `install:mongo.sh` | Idempotency tied to Vagrant/Homestead hostname. On any other host these scripts re-run destructively. |
| H3 | `rm -rf /var/lib/mysql /var/log/mysql /etc/mysql` unconditional | `install:maria.sh:34-36` | Runs every time when marker is absent (which is "every time on a non-Homestead host"). Wipes any pre-existing data without confirmation. |
| H4 | `add-apt-repository ppa:certbot/certbot` | `install:certbot.sh:2` | PPA was deprecated by Let's Encrypt in 2020. Modern guidance is `snap install certbot` or the official packages. |
| H5 | Hardcoded `php8.0-fpm` socket in vhost templates | `nginx:host.sh:31`, `nginx:laravel.sh:31`, `install:phpmyadmin.sh:6` | Conflicts with the PHP 8.2 installer in the same tree. Generates broken vhosts. |
| H6 | `apt install phpmyadmin` + `ln -s /usr/share/phpmyadmin /var/www/html` | `install:phpmyadmin.sh:3-4` | phpMyAdmin has a long history of public-facing CVEs; this exposes it at `/phpmyadmin` by default. |
| H7 | `mysql_secure_installation` invoked non-interactively | `install:mysql.sh:18` | `mysql_secure_installation` reads stdin; running it inside another script with no piped answers will leave it half-configured. |

## Medium

| # | Pattern | Files | Why |
|---|---------|-------|-----|
| M1 | Broken installer: `apt install -packages/extentions- -y` | `install:php7.sh:6` | Literal copy-paste of a placeholder; the install fails. Whole file should be deleted or rewritten. |
| M2 | Defined-but-never-called `installPHPPackages` | `install:php.sh` | Function declared, never invoked. Dead code; users expect the modules to install but they don't. |
| M3 | `install:server-env.sh` near-duplicate of `install:nginx.sh` | both | Redundant. |
| M4 | `crontab -u "$user"` after `chmod`-less touch of `/var/spool/cron/root` | `add:cron.sh` | The touched file is then `crontab -u`'d to a different user; the path-shape is wrong (`var/spool/cron/root` without leading `/`). |
| M5 | `sudo chgrp -R www-data` on Laravel files | `laravel:file-perms.sh:7` | `www-data` group hardcoded — fine on Debian/Ubuntu, wrong on RHEL/CentOS (`apache`/`nginx`). |
| M6 | `php artisan storage:link --force` | `laravel:file-perms.sh:18` | Idempotent in Laravel ≥ 5.5 only; older versions error. |
| M7 | Hardcoded MongoDB 3.4 / Maria 10.2 / xenial repo line | `install:mongo.sh`, `install:maria.sh` | These versions are EOL and the xenial repo is gone. Will fail on install. |

## Low

| # | Pattern | Files | Why |
|---|---------|-------|-----|
| L1 | Typo in path: `alliases/` | `configurators/alliases/` | Cosmetic; rename. |
| L2 | "Y\|n" prompt parsing accepts only `y` / `yes` / `Y` | most configurators | Doesn't handle `n` / `no` — falls through to "yes" on anything not in the accept list. |
| L3 | Bare `read s` without timeout / -p | most configurators | Hangs forever in non-interactive contexts. |
| L4 | Empty stubs: `scripts/help.sh`, `docs/`, `scripts/security/` | (those paths) | Looks like placeholder dirs. |

## Outcome

The Critical + High items above mean **almost every installer in
`ubuntu/` needs a redesign before it's safe to ship under shimkit**.
Re-implementing on the Docker-by-default path (per the maintainer's
charter expansion) sidesteps every Critical:

- **C1** (apparmor disable) — N/A inside a container.
- **C2 / C3** (DB exposed to network) — N/A by default; user opts in
  by binding a port at `docker run -p` time, and we generate the
  container with auth required.
- **C4** (apt-key) — modern Docker official images don't need it.
- **C5** (curl|bash node) — use the `node:` official image.

The container-first design also fixes most High items (H1–H4) without
any per-tool effort. Host-mutating mode (`--on-host`) would still
need to redesign each script from scratch — that's the explicit
opt-in trade-off documented in the charter.
