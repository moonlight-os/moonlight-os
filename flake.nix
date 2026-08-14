{
  # A flake for the host PC half only -- the ISO itself is built by ./build.sh
  # in a container, not by Nix.
  #
  # It exists so the agent is usable on NixOS before (and regardless of)
  # nixpkgs having it:
  #
  #     nix run github:MopigamesYT/moonlight-os#mlos-host-utils -- pair
  #
  # and so `nix build` here checks that packaging/nix/package.nix still
  # builds, against this checkout rather than a released tag.
  description = "USB passthrough agent for the PC you stream from with Moonlight OS";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      packages = forAllSystems (pkgs: rec {
        # The same derivation nixpkgs gets, pointed at this working tree
        # instead of a tagged tarball -- one definition, so the packaged
        # build and the local one cannot drift apart.
        mlos-host-utils = (pkgs.callPackage ./packaging/nix/package.nix { }).overrideAttrs (old: {
          src = self;
          version = "${old.version}-unstable-${self.shortRev or "dirty"}";
        });
        default = mlos-host-utils;
      });

      nixosModules = rec {
        mlos-host-utils = {
          imports = [ ./packaging/nix/module.nix ];
          # Until nixpkgs carries the package, point the module's default at
          # this flake's build for the host's own system.
          nixpkgs.overlays = [ self.overlays.default ];
        };
        default = mlos-host-utils;
      };

      overlays.default = final: prev: {
        mlos-host-utils = self.packages.${final.system}.mlos-host-utils;
      };

      # `nix flake check` on its own only proves nixosModules is shaped like a
      # module.  This forces the module through a real NixOS evaluation, which
      # is where an option that does not exist or a package that is not in the
      # overlay actually shows up -- and it costs an eval, not a system build.
      checks = forAllSystems (
        pkgs:
        let
          machine = nixpkgs.lib.nixosSystem {
            modules = [
              self.nixosModules.default
              {
                nixpkgs.hostPlatform = pkgs.stdenv.hostPlatform.system;
                boot.loader.grub.devices = [ "/dev/sda" ];
                fileSystems."/" = {
                  device = "/dev/sda1";
                  fsType = "ext4";
                };
                system.stateVersion = "25.05";
                services.mlos-host-utils = {
                  enable = true;
                  openFirewall = true;
                };
              }
            ];
          };
        in
        {
          package = self.packages.${pkgs.stdenv.hostPlatform.system}.mlos-host-utils;
          nixos-module = pkgs.writeText "mlos-host-utils-module-eval" (
            builtins.toJSON {
              inherit (machine.config.systemd.services.mlos-host-utils) path;
              exec = machine.config.systemd.services.mlos-host-utils.serviceConfig.ExecStart;
              modules = machine.config.boot.kernelModules;
              ports = machine.config.networking.firewall.allowedTCPPorts;
            }
          );
        }
      );

      formatter = forAllSystems (pkgs: pkgs.nixfmt-rfc-style);
    };
}
