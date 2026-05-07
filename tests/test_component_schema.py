import math

from qsim.schemas.components import SystemComponentSpec


def test_transmon_component_derives_rad_s_fields_from_hz_parameters():
    comp = SystemComponentSpec.from_dict(
        {
            "id": "q0",
            "type": "transmon",
            "basis": {"kind": "nlevel", "levels": 3},
            "parameters": {
                "freq_Hz": 5.0e9,
                "anharmonicity_Hz": -2.0e8,
            },
        }
    )

    assert comp.omega_rad_s == 2.0 * math.pi * 5.0e9
    assert comp.anharmonicity_rad_s == 2.0 * math.pi * -2.0e8
