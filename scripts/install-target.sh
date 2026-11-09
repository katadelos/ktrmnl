#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    printf '%s\n' "usage: $0 DESTDIR" >&2
    exit 2
fi

destdir=$1
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
app_dir="$destdir/usr/share/ktrmnl"
install -d "$app_dir/integration" "$destdir/usr/bin" "$destdir/usr/share/k2/applications" \
    "$destdir/usr/share/k2/features"
for directory in ktrmnl qml assets translations; do
    install -d "$app_dir/$directory"
    rsync -a --delete --exclude .DS_Store --exclude __pycache__ --exclude '*.pyc' \
        "$source_dir/$directory/" "$app_dir/$directory/"
done
install -m 0644 "$source_dir/menu.json" "$source_dir/config.example.json" "$app_dir/"
install -m 0755 "$source_dir/bin/ktrmnl" "$destdir/usr/bin/ktrmnl"
install -m 0644 "$source_dir/integration/application.json" \
    "$destdir/usr/share/k2/applications/ktrmnl.json"
install -m 0644 "$source_dir/integration/feature.json" \
    "$destdir/usr/share/k2/features/ktrmnl.json"
install -m 0644 "$source_dir/integration/nickelmenu" "$app_dir/integration/nickelmenu"
