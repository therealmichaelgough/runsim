using UnrealBuildTool;

public class RunsimViewer : ModuleRules
{
	public RunsimViewer(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
			"InputCore",
			// gaits_ue.json is parsed with FJsonSerializer at startup.
			"Json",
			"JsonUtilities",
			// the terrain heightfield chunks (engine plugin, enabled by default)
			"ProceduralMeshComponent"
		});

		PrivateDependencyModuleNames.AddRange(new string[] { });
	}
}
