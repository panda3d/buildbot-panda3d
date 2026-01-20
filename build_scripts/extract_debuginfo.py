#!/usr/bin/env python3
"""
Extract debug info from built binaries based on wheel contents.

Usage: extract_debuginfo.py <build_dir> <commit_id> <whl_file>...

Output: debuginfo.zip
"""
import os
import subprocess
import sys
import zipfile
from pathlib import Path


def get_build_id(filepath):
    """Extract build-id from an ELF file."""
    result = subprocess.run(
        ['readelf', '-n', filepath],
        capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        if 'Build ID:' in line:
            return line.split('Build ID:')[1].strip()
    return None


def extract_debuginfo(src, dst):
    """Extract debug info from src to dst."""
    subprocess.run(
        ['objcopy', '--only-keep-debug', src, dst],
        check=True
    )


def find_in_build_tree(build_dir, filename):
    """Find a file in the build tree by name."""
    # Try common locations
    candidates = list(build_dir.glob(f'**/{filename}'))
    if candidates:
        return candidates[0]
    return None


def write_metadata(zf, path, content):
    """Write a metadata file with proper permissions."""
    info = zipfile.ZipInfo(path)
    info.external_attr = 0o644 << 16  # rw-r--r--
    zf.writestr(info, content)


def main():
    build_dir = Path(sys.argv[1])
    commit_id = sys.argv[2]
    whl_files = sys.argv[3:]

    if not whl_files:
        sys.exit("No wheel files specified")

    output_zip = Path('debuginfo.zip')
    #source_prefix = os.getcwd().lstrip('/') + '/'
    source_prefix = 'build/'

    # Track which build-ids we've already processed
    processed = {}  # build_id -> (build_tree_path, whl_path)

    for whl_file in whl_files:
        whl_path = Path(whl_file)
        if not whl_path.exists():
            print(f"Skipping {whl_file}")
            continue

        opt_prefix = 'opt/' if '+opt' in whl_file else ''

        print(f"Scanning {whl_file}...")

        with zipfile.ZipFile(whl_path, 'r') as whl:
            for name in whl.namelist():
                # Look for shared libraries
                if not (name.endswith('.so') or '.so.' in name):
                    continue

                filename = os.path.basename(name)

                # Find corresponding unstripped file in build tree
                build_path = find_in_build_tree(build_dir, filename)
                if not build_path:
                    print(f"  {filename}: not found in build tree, skipping")
                    continue

                build_id = get_build_id(build_path)
                if not build_id:
                    print(f"  {filename}: no build-id, skipping")
                    continue

                # Skip if already processed
                if build_id in processed:
                    print(f"  {filename}: already processed (same build-id)")
                    continue

                whl_inner = f"{opt_prefix}{whl_path.name}/{name}"
                processed[build_id] = (build_path, whl_inner)
                print(f"  {filename}: {build_id}")

    print(f"\nPackaging {len(processed)} unique binaries...")

    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for build_id, (build_path, whl_inner) in processed.items():
            prefix = build_id[:2]
            base_path = f"buildid/{prefix}/{build_id}"

            # Extract and add debuginfo
            debuginfo_tmp = f"/tmp/{build_id}.debug"
            try:
                extract_debuginfo(build_path, debuginfo_tmp)
                zf.write(debuginfo_tmp, f"{base_path}/debuginfo")
            finally:
                if os.path.exists(debuginfo_tmp):
                    os.unlink(debuginfo_tmp)

            # Add metadata
            write_metadata(zf, f"{base_path}/.commit-id", commit_id + "\n")
            write_metadata(zf, f"{base_path}/.source-prefix", source_prefix + "\n")
            write_metadata(zf, f"{base_path}/.whl-path", whl_inner + "\n")

    print(f"Created {output_zip}")


if __name__ == '__main__':
    main()
