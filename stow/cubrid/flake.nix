{
  description = "CUBRID development environment flake";

  inputs = { nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable"; };

  outputs = { self, nixpkgs }:
    let
      # Declare supported systems
      supportedSystems = [ "x86_64-linux" ];

      # Helper function to generate per-system attributes
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;

      # Get pkgs for each system
      nixpkgsFor = forAllSystems (system: import nixpkgs { inherit system; });
    in {
      devShells = forAllSystems (system:
        let pkgs = nixpkgsFor.${system};
        in {
          default = pkgs.mkShell {

            packages = with pkgs; [
              flex
              bison
              ncurses
              cmake
              ninja
              binutils
              ccache
              gcc13
              zsh
              direnv
              elfutils
              libsystemtap
            ];

            shellHook = ''
              export CC=${pkgs.gcc13}/bin/gcc
              export CXX=${pkgs.gcc13}/bin/g++
            '';
          };
        });
    };
}
