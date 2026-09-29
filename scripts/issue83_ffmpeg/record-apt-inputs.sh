#!/usr/bin/env bash
set -euo pipefail

# Preserve the signed snapshot's archive hashes for every installed build package.
package_list=$1
output_file=$2
printf 'package version source archive_path sha256\n' > "$output_file"

while read -r package version; do
  record=$(apt-cache show "$package=$version" | awk -v expected_package="$package" -v expected_version="$version" '
    BEGIN { source = expected_package }
    /^Package:/ { package = $2 }
    /^Version:/ { version = $2 }
    /^Source:/ { source = $2 }
    /^Filename:/ { archive_path = $2 }
    /^SHA256:/ { sha256 = $2 }
    /^$/ {
      if (package == expected_package && version == expected_version && archive_path != "" && sha256 != "") {
        print expected_package, expected_version, source, archive_path, sha256
        found = 1
        exit
      }
      package = version = archive_path = sha256 = ""
      source = expected_package
    }
    END {
      if (!found && package == expected_package && version == expected_version && archive_path != "" && sha256 != "") {
        print expected_package, expected_version, source, archive_path, sha256
        found = 1
      }
      if (!found) exit 1
    }
  ')
  printf '%s\n' "$record" >> "$output_file"
done < "$package_list"
