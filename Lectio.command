#!/bin/zsh
# Double-clic : active l'environnement conda "lectio" puis lance l'application.
cd "$(dirname "$0")"
[ -f ~/.zshrc ] && source ~/.zshrc 2>/dev/null
source "$(conda info --base)/etc/profile.d/conda.sh" || { echo "conda introuvable"; read -k1; exit 1; }
conda activate lectio || { echo "environnement lectio introuvable"; read -k1; exit 1; }
cd desktop && npm run app
