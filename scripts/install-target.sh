#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    printf '%s\n' "usage: $0 DESTDIR" >&2
    exit 2
fi

destdir=$1
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
app_dir="$destdir/usr/share/ktrmnl2"
install -d "$app_dir/integration" "$destdir/usr/bin" "$destdir/usr/share/k2/applications" \
    "$destdir/usr/share/k2/features"
for directory in ktrmnl2 qml assets translations; do
    install -d "$app_dir/$directory"
    rsync -a --delete --exclude .DS_Store --exclude __pycache__ --exclude '*.pyc' \
        "$source_dir/$directory/" "$app_dir/$directory/"
done
install -m 0644 "$source_dir/menu.json" "$source_dir/config.example.json" "$app_dir/"
install -m 0755 "$source_dir/bin/ktrmnl2" "$destdir/usr/bin/ktrmnl2"
install -m 0644 "$source_dir/integration/application.json" \
    "$destdir/usr/share/k2/applications/ktrmnl2-k2-variant.json"
install -m 0644 "$source_dir/integration/feature.json" \
    "$destdir/usr/share/k2/features/ktrmnl2-k2-variant.json"
install -m 0644 "$source_dir/integration/nickelmenu" "$app_dir/integration/nickelmenu"
