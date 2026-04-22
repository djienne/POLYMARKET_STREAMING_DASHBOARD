#!/usr/bin/env bash
# Bootstrap a fresh Ubuntu VPS for Polymarket / BTC_pricer-style workloads,
# without requiring the BTC_pricer_15m repo to already exist.
#
# Example:
#   bash scripts/setup_btc_pricer_15m_vps.sh
#
# Optional:
#   INSTALL_DOCKER=1    -> install docker + docker compose
#   INSTALL_QUANTLIB=1  -> pip install QuantLib
#   INSTALL_TRADING_STACK=1 -> install common Python deps used by the bot
#   CLONE_REPO_URL=git@github.com:your-user/BTC_pricer_15m.git
#   REPO_DIR=~/BTC_pricer_15m
#   ENV_NAME=btc_pricer
#   PYTHON_VERSION=3.11
set -euo pipefail

CLONE_REPO_URL="${CLONE_REPO_URL:-}"
REPO_DIR="${REPO_DIR:-$HOME/BTC_pricer_15m}"
MINICONDA_DIR="${MINICONDA_DIR:-$HOME/miniconda3}"
ENV_NAME="${ENV_NAME:-btc_pricer}"
PYTHON_VERSION="${PYTHON_VERSION:-3.11}"
INSTALL_DOCKER="${INSTALL_DOCKER:-0}"
INSTALL_QUANTLIB="${INSTALL_QUANTLIB:-0}"
INSTALL_TRADING_STACK="${INSTALL_TRADING_STACK:-1}"

if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo is required on the VPS."
  exit 1
fi

if [[ ! -f /etc/os-release ]]; then
  echo "Unsupported system: /etc/os-release not found."
  exit 1
fi

. /etc/os-release
if [[ "${ID:-}" != "ubuntu" ]]; then
  echo "This script is written for Ubuntu. Detected: ${ID:-unknown}"
  exit 1
fi

log() {
  echo "[setup] $*"
}

ensure_apt_packages() {
  log "Installing base system packages"
  sudo apt update
  sudo apt install -y \
    git \
    curl \
    wget \
    build-essential \
    python3-dev \
    python3-venv \
    tmux
}

ensure_miniconda() {
  if [[ -x "${MINICONDA_DIR}/bin/conda" ]]; then
    log "Miniconda already present at ${MINICONDA_DIR}"
    return
  fi

  log "Installing Miniconda to ${MINICONDA_DIR}"
  local installer="/tmp/miniconda.sh"
  wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O "${installer}"
  bash "${installer}" -b -p "${MINICONDA_DIR}"
}

init_conda() {
  # shellcheck disable=SC1091
  eval "$("${MINICONDA_DIR}/bin/conda" shell.bash hook)"
}

ensure_conda_env() {
  init_conda

  if conda env list | awk '{print $1}' | grep -Fxq "${ENV_NAME}"; then
    log "Conda env ${ENV_NAME} already exists"
  else
    log "Creating conda env ${ENV_NAME} with Python ${PYTHON_VERSION}"
    conda create -n "${ENV_NAME}" "python=${PYTHON_VERSION}" -y
  fi

  conda activate "${ENV_NAME}"
}

install_python_deps() {
  init_conda
  conda activate "${ENV_NAME}"

  python -m pip install --upgrade pip
  if [[ "${INSTALL_TRADING_STACK}" == "1" ]]; then
    log "Installing common trading/calibration Python dependencies"
    python -m pip install \
      numpy \
      scipy \
      requests \
      PyYAML \
      pandas \
      matplotlib \
      python-dotenv \
      py-clob-client \
      web3 \
      python-dateutil
  fi

  if [[ "${INSTALL_QUANTLIB}" == "1" ]]; then
    log "Installing QuantLib"
    python -m pip install QuantLib
  fi
}

ensure_repo() {
  if [[ -z "${CLONE_REPO_URL}" ]]; then
    log "No CLONE_REPO_URL provided; skipping repo clone"
    return
  fi

  if [[ -d "${REPO_DIR}/.git" ]]; then
    log "Repo already exists at ${REPO_DIR}; pulling latest default branch"
    git -C "${REPO_DIR}" fetch --all --prune
    git -C "${REPO_DIR}" pull --ff-only || true
  else
    log "Cloning ${CLONE_REPO_URL} into ${REPO_DIR}"
    git clone "${CLONE_REPO_URL}" "${REPO_DIR}"
  fi
}

install_docker() {
  if command -v docker >/dev/null 2>&1; then
    log "Docker already installed"
    return
  fi

  log "Installing Docker via get.docker.com"
  local installer="/tmp/get-docker.sh"
  curl -fsSL https://get.docker.com -o "${installer}"
  sudo sh "${installer}"
  sudo usermod -aG docker "${USER}" || true
}

print_next_steps() {
  cat <<EOF

[setup] Done.

Next steps:
1. Copy your real config files / .env / secrets to:
   ${REPO_DIR}

2. Activate the env:
   source "${MINICONDA_DIR}/etc/profile.d/conda.sh"
   conda activate "${ENV_NAME}"

3. If you want the repo on this VPS, either clone it now:
   git clone <YOUR_BTC_PRICER_15M_REPO_URL> ${REPO_DIR}

4. Manual trader mode:
   cd "${REPO_DIR}"
   python -m scripts.trader.main --discover
   python -m scripts.trader.main --mode trader -v

5. If Docker was installed and you want grid mode:
   cd "${REPO_DIR}"
   docker compose up -d --build
   docker compose logs -f grid

If Docker was newly installed, you may need to log out and back in before
the non-root docker group membership fully applies.
EOF
}

ensure_apt_packages
ensure_miniconda
ensure_conda_env
install_python_deps
ensure_repo

if [[ "${INSTALL_DOCKER}" == "1" ]]; then
  install_docker
fi

print_next_steps
