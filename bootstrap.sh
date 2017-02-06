rsync --exclude ".git/" \
	--exclude ".DS_Store" \
	--exclude ".osx" \
	--exclude "bootstrap.sh" \
    --exclude "brew.sh" \
    --exclude "LICENSE-MIT.txt" \
	--exclude "README.md" \
    --exclude "Sublime Text 3.sh" \
	-avh --no-perms . ~;

for file in ~/.{aliases,bash_profile,exports,zshrc}; do
    source $file
done;
