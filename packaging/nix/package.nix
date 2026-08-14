# Ready to drop into nixpkgs as pkgs/by-name/ml/mlos-host-utils/package.nix.
#
# Nothing here is templated, unlike the winget and AUR manifests: a nixpkgs
# package is updated by a reviewed pull request, not by our CI, so the version
# and hash in this file are real values.  `packaging/nix/update.sh <tag>`
# bumps both, and passthru.updateScript lets nixpkgs' own update bot do it
# once the package is in the tree.
{
  lib,
  buildGoModule,
  fetchFromGitHub,
  nix-update-script,
}:

buildGoModule (finalAttrs: {
  pname = "mlos-host-utils";
  version = "0.1.3";

  src = fetchFromGitHub {
    owner = "MopigamesYT";
    repo = "moonlight-os";
    tag = "v${finalAttrs.version}";
    hash = "sha256-TZDaNAV+v7reKiBllkbESQ1/n1ItGKFDNGMUcuNcXcM=";
  };

  # nixpkgs-vet fails a new package without this, and it is where nixpkgs is
  # going anyway: the builder gets the attributes as real data structures
  # rather than as shell-mangled strings.
  __structuredAttrs = true;

  # The agent is one directory of a repository that is otherwise an ISO
  # build, so the Go module is not at the root.
  modRoot = "host-utils";

  # Standard library only -- there is no go.sum and nothing to vendor.
  vendorHash = null;

  ldflags = [
    "-s"
    "-w"
    "-X main.Version=${finalAttrs.version}"
  ];

  passthru.updateScript = nix-update-script { };

  meta = {
    description = "USB passthrough agent for the PC you stream from with Moonlight OS";
    longDescription = ''
      The host PC half of USB passthrough for Moonlight OS. Moonlight OS says
      which USB devices are plugged into the thin client; this agent attaches
      them to the machine the game is actually running on, over USB/IP.

      On NixOS, use services.mlos-host-utils rather than `mlos-host-utils
      install`: the imperative installer writes a systemd unit and fetches a
      usbip package, and neither survives the next rebuild.
    '';
    homepage = "https://github.com/MopigamesYT/moonlight-os";
    changelog = "https://github.com/MopigamesYT/moonlight-os/releases/tag/v${finalAttrs.version}";
    license = lib.licenses.mpl20;
    mainProgram = "mlos-host-utils";
    maintainers = [ ];
    platforms = lib.platforms.linux;
  };
})
