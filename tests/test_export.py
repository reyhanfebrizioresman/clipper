from clipper.campaign import Campaign
from clipper.export import platform_variants, ExportSpec

CAMP = Campaign(slug="x", nama="X", cpm_rp=1000, durasi_min_s=15, durasi_maks_s=180,
                platform=["TikTok", "Instagram"], hashtag=["#A", "#B", "#C"])

def test_tiktok_caption_is_single_line_others_keep_breaks():
    v = {e.platform: e for e in platform_variants(CAMP, "Hook kuat", ["tiktok", "instagram"])}
    assert "\n" not in v["tiktok"].caption
    assert "\n" in v["instagram"].caption

def test_all_variants_keep_mandatory_hashtags():
    for e in platform_variants(CAMP, "Hook", ["tiktok", "instagram", "youtube"]):
        assert all(h in e.caption for h in CAMP.hashtag)

def test_default_platforms_from_campaign_case_insensitive():
    v = platform_variants(CAMP, "Hook")
    assert [e.platform for e in v] == ["tiktok", "instagram"]
    assert all(isinstance(e, ExportSpec) and e.maks_durasi > 0 and e.catatan for e in v)
