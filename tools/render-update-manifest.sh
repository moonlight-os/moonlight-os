#!/bin/sh
set -eu

if [ "$#" -ne 6 ]; then
	echo "usage: $0 VERSION TAG ISO SHA256 SIZE OUTPUT" >&2
	exit 2
fi

version=$1
tag=$2
iso=$3
sha256=$4
size=$5
output=$6

case "$tag" in
	v*-*)
		# Prerelease discovery does not use /releases/latest, so bind the
		# signed metadata to the exact tag selected from the releases API.
		printf 'format=2\nversion=%s\ntag=%s\niso=%s\nsha256=%s\nsize=%s\n' \
			"$version" "$tag" "$iso" "$sha256" "$size" > "$output"
		;;
	v*)
		# Moonlight OS 0.2.6 only accepts format 1. Keep stable metadata
		# backward-compatible so every installed system can bootstrap into
		# the channel-aware updater before it opts into Beta.
		printf 'format=1\nversion=%s\niso=%s\nsha256=%s\nsize=%s\n' \
			"$version" "$iso" "$sha256" "$size" > "$output"
		;;
	*)
		echo "invalid release tag: $tag" >&2
		exit 2
		;;
esac
