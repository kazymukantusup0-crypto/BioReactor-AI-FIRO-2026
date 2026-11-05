"""Conservative mass-basis concentration calculation for explicit dilution inputs."""
import math


def calculate_vs_concentration(data):
    required = ('vs_mass_kg', 'mass_kg', 'dilution_water_l')
    missing = [name for name in required if data.get(name) is None]
    if missing:
        return {
            'status': 'needs_input',
            'missing': missing,
            'message': 'Measured VS mass, wet feed mass, and dilution-water volume are required.',
        }

    vs_mass = float(data['vs_mass_kg'])
    feed_mass = float(data['mass_kg'])
    water_volume = float(data['dilution_water_l'])
    if not all(math.isfinite(v) for v in (vs_mass,feed_mass,water_volume)) or vs_mass <= 0 or feed_mass <= 0 or water_volume < 0 or vs_mass > feed_mass:
        return {'status': 'error', 'message': 'Feed and VS masses must be positive, water nonnegative, all finite; VS cannot exceed wet feed mass.'}

    water_density = 1.0  # kg/L approximate, explicitly disclosed in the result
    total_mass = feed_mass + water_volume * water_density
    fraction = vs_mass / total_mass
    return {
        'status': 'ok',
        'message': (
            f'Wet-mass VS concentration is {fraction * 100:.4g}% w/w under the stated water-density assumption. '
            'A volumetric concentration is not determined without feed volume or density.'
        ),
        'vs_mass_kg': vs_mass,
        'feed_wet_mass_kg': feed_mass,
        'dilution_water_l': water_volume,
        'assumed_water_density_kg_l': water_density,
        'total_wet_mass_after_dilution_kg': total_mass,
        'vs_mass_fraction_wet': fraction,
        'vs_percent_wet_mass': fraction * 100,
        'volumetric_concentration_kg_vs_m3': None,
        'missing_for_volumetric_concentration': ['feed_volume_l_or_feed_density_kg_l'],
        'input_provenance': data.get('scenario_input_provenance',{}),
        'assumptions': [
            'Added water density approximated as 1.0 kg/L; not measured for this batch.',
            'Complete mixing and no mass loss.',
            'Only explicit feed and water mass are included; inoculum or other additions are excluded.',
        ] + (['Water amount is a user hypothetical scenario, not a confirmed actual addition.'] if data.get('scenario_input_provenance') else []),
    }
