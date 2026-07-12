from app.services.surgeries import SurgeryValidationError, build_complication_event


def test_build_complication_requires_details_when_occurred():
    try:
        build_complication_event(
            occurred=True,
            complication_type=None,
            surgical_stage=None,
            vitreous_loss=None,
            anterior_vitrectomy=None,
            fragments_to_posterior=None,
            retina_intervention=None,
            iol_position=None,
            capsular_tension_ring=None,
            segment_ring_suture=None,
            f2_assistant_help=None,
        )
        assert False, "Expected SurgeryValidationError"
    except SurgeryValidationError:
        pass


def test_build_complication_clears_details_when_not_occurred():
    event = build_complication_event(
        occurred=False,
        complication_type="pcr",
        surgical_stage="capsulorhexis",
        vitreous_loss="true",
        anterior_vitrectomy="true",
        fragments_to_posterior="false",
        retina_intervention="false",
        iol_position="bag",
        capsular_tension_ring="true",
        segment_ring_suture="false",
        f2_assistant_help="true",
    )
    assert event.occurred is False
    assert event.complication_type is None
    assert event.surgical_stage is None


def test_build_complication_with_full_details():
    event = build_complication_event(
        occurred=True,
        complication_type="zonulodialysis",
        surgical_stage="hydrodissection",
        vitreous_loss="false",
        anterior_vitrectomy="false",
        fragments_to_posterior="false",
        retina_intervention="false",
        iol_position="bag",
        capsular_tension_ring="true",
        segment_ring_suture="true",
        f2_assistant_help="false",
    )
    assert event.occurred is True
    assert event.complication_type == "zonulodialysis"
    assert event.capsular_tension_ring is True
    assert event.segment_ring_suture is True
    assert event.f2_assistant_help is False
