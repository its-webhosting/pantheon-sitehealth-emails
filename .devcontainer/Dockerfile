FROM node:24-trixie

ARG TZ
ENV TZ="$TZ"

ARG CLAUDE_CODE_VERSION=latest

# Install basic development tools and iptables/ipset
RUN apt-get update && apt-get install -y --no-install-recommends \
  less \
  git \
  procps \
  sudo \
  fzf \
  man-db \
  unzip \
  gnupg2 \
  gh \
  iptables ipset iproute2 \
  dnsutils \
  aggregate \
  jq \
  nano \
  vim \
  locate \
  curl ca-certificates \
  build-essential default-mysql-client python3-dev \
  php-common php-cli php-zip php-mysql php-curl php-mbstring php-xml php-dev wget \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

ARG USERNAME=node

# Ensure default node user has access to /usr/local/share
RUN mkdir -p /usr/local/share/npm-global && \
  chown -R $USERNAME:$USERNAME /usr/local/share

# Persist bash history.
RUN SNIPPET="export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
  && mkdir /commandhistory \
  && touch /commandhistory/.bash_history \
  && chown -R $USERNAME:$USERNAME /commandhistory

# Set `DEVCONTAINER` environment variable to help with orientation
ENV DEVCONTAINER=true

# Create workspace and config directories and set permissions
RUN mkdir -p /workspace /home/$USERNAME/.claude /home/$USERNAME/software_versions && \
  chown -R $USERNAME:$USERNAME /workspace /home/$USERNAME/.claude /home/$USERNAME/software_versions

WORKDIR /workspace

ARG GIT_DELTA_VERSION=0.18.2
RUN ARCH=$(dpkg --print-architecture) && \
  wget "https://github.com/dandavison/delta/releases/download/${GIT_DELTA_VERSION}/git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb" && \
  sudo dpkg -i "git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb" && \
  rm "git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb"

# Install Starship shell prompt
RUN curl -sS https://starship.rs/install.sh >/tmp/install.sh \
  && sh /tmp/install.sh --yes \
  && rm /tmp/install.sh

# install RTK
ADD https://api.github.com/repos/rtk-ai/rtk/tags?per_page=1 /home/$USERNAME/software_versions/rtk_version.json
RUN curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/master/install.sh \
  | env RTK_INSTALL_DIR=/usr/local/bin sh

RUN chown -R $USERNAME:$USERNAME /home/$USERNAME/software_versions

# Install uv / Python
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN mkdir -p /workspace/.venv && chown -R $USERNAME:$USERNAME /workspace
RUN echo '[ -f /workspace/.venv/bin/activate ] && source /workspace/.venv/bin/activate' >> /home/$USERNAME/.bashrc
ENV UV_CACHE_DIR=/workspace/.venv/cache
ENV UV_PYTHON_INSTALL_DIR=/workspace/.venv/install

# PHP stuff
COPY --from=composer/composer:latest-bin /composer /usr/bin/composer
ADD https://api.github.com/repos/pantheon-systems/terminus/tags?per_page=1 /home/$USERNAME/software_versions/terminus.json
RUN curl -L https://github.com/pantheon-systems/terminus/releases/latest/download/terminus.phar --output /usr/local/bin/terminus \
  && chmod 755 /usr/local/bin/terminus

# awscli
RUN cd /tmp \
  && curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" \
  && unzip awscliv2.zip \
  && /bin/sh aws/install \
  && rm -rf awscliv2.zip aws


# Copy and set up the container start script
COPY container-start.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/container-start.sh && \
  echo "$USERNAME ALL=(root) NOPASSWD: /usr/local/bin/container-start.sh" > /etc/sudoers.d/container-start && \
  chmod 0440 /etc/sudoers.d/container-start

# Set up non-root user
USER $USERNAME

# Install global packages
ENV NPM_CONFIG_PREFIX=/usr/local/share/npm-global
ENV PATH=$PATH:/usr/local/share/npm-global/bin

# Set the default shell to zsh rather than sh
ENV SHELL=/bin/bash

# Set the default editor and visual
ENV EDITOR=vim
ENV VISUAL=vim

# Configure the Starship shell prompt
RUN echo 'eval "$(starship init bash)"' >> /home/$USERNAME/.bashrc
RUN mkdir -p ~/.config \
  && starship preset catppuccin-powerline -o ~/.config/starship.toml \
  && starship config line_break.disabled false

RUN cat <<EOF >> /home/$USERNAME/.bashrc

# Force correct terminal size (needed for Zed terminals)
old_stty=\$(stty -g)
stty raw -echo
printf "\0337\033[r\033[999;999H\033[6n\033[18t"
read -t 1 -d c c0
c1=\$(echo "\$c0" | perl -a -n -F';' -e 'print "rows " . int(\$F[2]) . " cols " . int(\$F[3]) . "\n";')
stty "\$old_stty"
stty \$c1
unset oldstty c0 c1

EOF


# Install mise
RUN curl https://mise.run | sh
RUN echo 'eval "$(/home/node/.local/bin/mise activate bash)"' >> /home/$USERNAME/.bashrc

# Install CodeGraph
ADD https://api.github.com/repos/colbymchenry/codegraph/tags?per_page=1 /home/$USERNAME/software_versions/codegraph_version.json
RUN npm install -g @colbymchenry/codegraph

# Install Claude
# The ADD forces everything after to not be cached when a new version is released.
ADD https://api.github.com/repos/anthropics/claude-code/tags?per_page=1 /home/$USERNAME/software_versions/claude_version.json
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}
RUN npm install -g tui-use

# Set up other stuff
COPY --chown=$USERNAME:$USERNAME terminus /home/$USERNAME/.terminus
COPY --chown=$USERNAME:$USERNAME ssh /home/$USERNAME/.ssh
RUN echo 'eval "$(ssh-agent -s)"' >> /home/$USERNAME/.bashrc

