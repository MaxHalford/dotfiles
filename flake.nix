{
  description = "Max Halford's dotfiles and NixOS hosts";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    hermes-agent.url = "github:NousResearch/hermes-agent/59004a62356f3a4697ab0fe8ad5086d2b405e2a6";
  };

  outputs =
    inputs@{
      nixpkgs,
      home-manager,
      hermes-agent,
      ...
    }:
    {
      nixosConfigurations.beelink-nixos = nixpkgs.lib.nixosSystem {
        system = "x86_64-linux";
        specialArgs = { inherit inputs; };
        modules = [
          ./nixos/beelink/configuration.nix
          home-manager.nixosModules.home-manager
          {
            home-manager.useGlobalPkgs = true;
            home-manager.useUserPackages = true;
            home-manager.extraSpecialArgs.hermesAgent = hermes-agent;
            home-manager.users.max = import ./nixos/beelink/home.nix;
          }
        ];
      };
    };
}
