import ast
import json
import os
import tempfile
from string import Formatter
import unittest

from coilforge.i18n import (
    TRANSLATIONS,
    Translator,
    localize_error,
    detect_language,
    language_from_kicad_config,
    normalize_language,
)
from coilforge.presets import (
    APPLICATION_PRESETS, MANUFACTURING_PRESETS, QUALITY_PRESETS,
)


class I18nTests(unittest.TestCase):
    def test_language_normalization(self):
        self.assertEqual("zh", normalize_language("zh_CN.UTF-8"))
        self.assertEqual("zh", normalize_language("简体中文"))
        self.assertEqual("en", normalize_language("English"))
        self.assertEqual("en", normalize_language("Deutsch"))

    def test_kicad_config_has_priority_over_system_locale(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "kicad_common.json")
            with open(path, "w", encoding="utf-8") as config_file:
                json.dump({"system": {"language": "简体中文"}}, config_file)
            self.assertEqual("zh", language_from_kicad_config(path))
            self.assertEqual(
                "zh",
                detect_language(
                    environ={"LANG": "en_US.UTF-8"},
                    locale_name="en_US",
                    kicad_config_path=path,
                ),
            )

    def test_kicad_settings_manager_path_is_used(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "kicad_common.json")
            with open(path, "w", encoding="utf-8") as config_file:
                json.dump({"system": {"language": "zh_TW"}}, config_file)

            class Manager(object):
                @staticmethod
                def GetUserSettingsPath():
                    return directory

            class PcbnewModule(object):
                SETTINGS_MANAGER = Manager

            self.assertEqual(
                "zh",
                detect_language(
                    pcbnew_module=PcbnewModule,
                    environ={"LANG": "en_US.UTF-8"},
                ),
            )

    def test_version_specific_config_directory_is_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            for version, language in (("9.0", "English"), ("10.99", "简体中文")):
                version_dir = os.path.join(directory, version)
                os.makedirs(version_dir)
                with open(
                        os.path.join(version_dir, "kicad_common.json"),
                        "w", encoding="utf-8") as config_file:
                    json.dump({"system": {"language": language}}, config_file)
            self.assertEqual(
                "en",
                detect_language(
                    kicad_version="9.0.6",
                    environ={"KICAD_CONFIG_HOME": directory},
                    platform_name="linux",
                    home=directory,
                    locale_name="zh_CN",
                ),
            )
            self.assertEqual(
                "zh",
                detect_language(
                    kicad_version="10.99.0",
                    environ={"KICAD_CONFIG_HOME": directory},
                    platform_name="linux",
                    home=directory,
                    locale_name="en_US",
                ),
            )

    def test_default_kicad_language_falls_back_to_system(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "kicad_common.json")
            with open(path, "w", encoding="utf-8") as config_file:
                json.dump({"system": {"language": "default"}}, config_file)
            self.assertEqual(
                "zh",
                detect_language(
                    environ={"LANG": "zh_CN.UTF-8"},
                    locale_name="zh_CN",
                    kicad_config_path=path,
                ),
            )

    def test_traditional_chinese_is_chinese(self):
        self.assertEqual("zh", normalize_language("繁體中文"))

    def test_wx_system_traditional_chinese_is_chinese(self):
        class LanguageInfo(object):
            CanonicalName = "zh_TW"
            Description = "Traditional Chinese"

        class Locale(object):
            @staticmethod
            def GetSystemLanguage():
                return 1

            @staticmethod
            def GetLanguageInfo(_language_id):
                return LanguageInfo()

        class WxModule(object):
            pass

        WxModule.Locale = Locale
        self.assertEqual(
            "zh",
            detect_language(
                wx_module=WxModule,
                environ={},
                locale_name="en_US",
                kicad_config_path="missing.json",
            ),
        )

    def test_other_system_languages_use_english(self):
        self.assertEqual(
            "en",
            detect_language(environ={"LANG": "de_DE.UTF-8"}, locale_name="de_DE"),
        )

    def test_configured_non_chinese_kicad_language_forces_english(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "kicad_common.json")
            with open(path, "w", encoding="utf-8") as config_file:
                json.dump({"system": {"language": "Deutsch"}}, config_file)
            self.assertEqual(
                "en",
                detect_language(
                    environ={"LANG": "zh_CN.UTF-8"},
                    kicad_config_path=path,
                ),
            )

    def test_translation_catalogs_have_matching_keys(self):
        self.assertEqual(
            set(TRANSLATIONS["en"]), set(TRANSLATIONS["zh"])
        )

    def test_translation_catalogs_do_not_repeat_literal_keys(self):
        source_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "coilforge", "i18n.py"
        )
        with open(source_path, "r", encoding="utf-8") as source_file:
            module = ast.parse(source_file.read())
        translation_node = next(
            node.value for node in module.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id == "TRANSLATIONS"
                for target in node.targets
            )
        )
        for language_node in translation_node.values:
            keys = [key.value for key in language_node.keys]
            self.assertEqual(len(keys), len(set(keys)))

    def test_static_translation_keys_used_by_runtime_exist(self):
        project_root = os.path.dirname(os.path.dirname(__file__))
        used = set()
        source_paths = [
            os.path.join(project_root, filename)
            for filename in os.listdir(project_root)
            if filename.endswith(".py")
        ]
        source_paths.extend(
            os.path.join(project_root, "coilforge", filename)
            for filename in os.listdir(os.path.join(project_root, "coilforge"))
            if filename.endswith(".py")
        )
        for source_path in source_paths:
            with open(source_path, "r", encoding="utf-8") as source_file:
                module = ast.parse(source_file.read())
            for node in ast.walk(module):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                function = node.func
                if not isinstance(function, ast.Attribute) or function.attr != "tr":
                    continue
                key = node.args[0]
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    used.add(key.value)
        missing = used - set(TRANSLATIONS["en"])
        self.assertEqual(set(), missing)

    def test_dynamic_translation_key_families_are_complete(self):
        required = set()
        required.update(
            "application_" + code for code in APPLICATION_PRESETS
        )
        required.update(
            "preset_description_" + code for code in APPLICATION_PRESETS
        )
        required.update(
            "manufacturing_" + code for code in MANUFACTURING_PRESETS
        )
        required.update("quality_" + code for code in QUALITY_PRESETS)
        required.update(
            "motor_layout_" + code for code in ("single", "radial", "linear")
        )
        required.update(
            "guide_hint_sizing_" + mode
            for mode in ("manual", "fit_turns", "fit_length")
        )
        required.update(
            "guide_hint_" + page for page in (
                "quick_setup", "board", "geometry", "placement",
                "multilayer", "options",
            )
        )
        for language in ("en", "zh"):
            self.assertEqual(
                set(), required - set(TRANSLATIONS[language]), language
            )

    def test_user_visible_ui_text_is_not_hardcoded(self):
        project_root = os.path.dirname(os.path.dirname(__file__))
        source_paths = [
            os.path.join(project_root, "coilforge", filename)
            for filename in ("interface.py", "ipc_ui.py", "legacy_plugin.py")
        ]
        offenders = []
        for source_path in source_paths:
            with open(source_path, "r", encoding="utf-8") as source_file:
                tree = ast.parse(source_file.read(), filename=source_path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                for keyword in node.keywords:
                    if keyword.arg not in ("label", "text", "title", "message"):
                        continue
                    value = keyword.value
                    if not (
                            isinstance(value, ast.Constant)
                            and isinstance(value.value, str)
                            and value.value.strip()):
                        continue
                    literal = value.value.strip()
                    if any(character.isalpha() for character in literal):
                        offenders.append((
                            os.path.basename(source_path), node.lineno, literal
                        ))
        self.assertEqual([], offenders)

    def test_translation_placeholders_match(self):
        formatter = Formatter()
        for key in TRANSLATIONS["en"]:
            english = {
                name for _literal, name, _format, _conversion
                in formatter.parse(TRANSLATIONS["en"][key]) if name
            }
            chinese = {
                name for _literal, name, _format, _conversion
                in formatter.parse(TRANSLATIONS["zh"][key]) if name
            }
            self.assertEqual(english, chinese, key)

    def test_sizing_mode_hints_explain_the_required_primary_input(self):
        for language in ("en", "zh"):
            for mode in ("manual", "fit_turns", "fit_length"):
                self.assertTrue(
                    TRANSLATIONS[language]["guide_hint_sizing_" + mode]
                )
        self.assertIn(
            "圈数", TRANSLATIONS["zh"]["guide_hint_sizing_fit_turns"]
        )
        self.assertIn(
            "目标长度", TRANSLATIONS["zh"]["guide_hint_sizing_fit_length"]
        )
        self.assertIn(
            "turn count", TRANSLATIONS["en"]["guide_hint_sizing_fit_turns"]
        )
        self.assertIn(
            "target length", TRANSLATIONS["en"]["guide_hint_sizing_fit_length"]
        )

    def test_ipc_manifest_user_text_is_bilingual(self):
        project_root = os.path.dirname(os.path.dirname(__file__))
        with open(
                os.path.join(project_root, "plugin.json"),
                "r", encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)
        descriptions = [
            manifest["description"], manifest["actions"][0]["description"],
        ]
        for description in descriptions:
            self.assertTrue(any("A" <= char <= "z" for char in description))
            self.assertTrue(any("\u4e00" <= char <= "\u9fff" for char in description))

    def test_guided_ui_and_author_strings_are_localized(self):
        self.assertEqual("Author: askstar", TRANSLATIONS["en"]["author_info"])
        self.assertEqual("作者：问星", TRANSLATIONS["zh"]["author_info"])
        for language in ("en", "zh"):
            self.assertIn("1", TRANSLATIONS[language]["section_quick_setup"])
            self.assertIn("7", TRANSLATIONS[language]["section_options"])
            self.assertTrue(TRANSLATIONS[language]["preview_empty"])

    def test_validation_feedback_is_actionable(self):
        self.assertIn("Suggested", TRANSLATIONS["en"]["invalid_number"])
        self.assertIn("建议", TRANSLATIONS["zh"]["invalid_number"])
        self.assertIn("{error}", TRANSLATIONS["en"]["validation_issue"])
        self.assertIn("{error}", TRANSLATIONS["zh"]["validation_issue"])

    def test_all_user_facing_error_codes_are_fully_localized(self):
        project_root = os.path.dirname(os.path.dirname(__file__))
        source_directory = os.path.join(project_root, "coilforge")
        codes = set()
        exception_types = {
            "GeometryError", "RuntimeError", "TypeError", "ValueError",
        }
        for filename in os.listdir(source_directory):
            if not filename.endswith(".py"):
                continue
            source_path = os.path.join(source_directory, filename)
            with open(source_path, "r", encoding="utf-8") as source_file:
                tree = ast.parse(source_file.read(), filename=source_path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Raise):
                    continue
                exception = node.exc
                if not isinstance(exception, ast.Call) or not exception.args:
                    continue
                function = exception.func
                name = (
                    function.id if isinstance(function, ast.Name)
                    else function.attr if isinstance(function, ast.Attribute)
                    else ""
                )
                code = exception.args[0]
                if (name in exception_types
                        and isinstance(code, ast.Constant)
                        and isinstance(code.value, str)
                        and "_" in code.value
                        and code.value.replace("_", "").isalnum()):
                    codes.add(code.value)
        self.assertTrue(codes)
        for language in ("en", "zh"):
            missing = codes - set(TRANSLATIONS[language])
            self.assertEqual(set(), missing, language)
            for code in codes:
                self.assertNotEqual(code, TRANSLATIONS[language][code])

    def test_localize_error_translates_known_codes_and_preserves_unknown(self):
        self.assertEqual(
            TRANSLATIONS["zh"]["kicad_via_type_unavailable"],
            localize_error(
                Translator("zh"), RuntimeError("kicad_via_type_unavailable")
            ),
        )
        self.assertEqual(
            "third-party diagnostic",
            localize_error(
                Translator("zh"), RuntimeError("third-party diagnostic")
            ),
        )

    def test_motor_spacing_errors_are_actionable_and_formatted(self):
        for language in ("en", "zh"):
            translator = Translator(language)
            radial = translator(
                "motor_array_radius_too_small",
                actual="25", minimum="31.5", unit="mm",
            )
            linear = translator(
                "motor_linear_pitch_too_small",
                actual="20", minimum="24", unit="mm",
            )
            self.assertNotIn("motor_array_radius_too_small", radial)
            self.assertNotIn("motor_linear_pitch_too_small", linear)
            self.assertIn("25", radial)
            self.assertIn("31.5", radial)
            self.assertIn("20", linear)
            self.assertIn("24", linear)

    def test_translator_formats_values(self):
        self.assertEqual("预计分段数：12", Translator("zh")("estimated_segments", count=12))

    def test_branding_accepts_a_version(self):
        self.assertEqual(
            "CoilForge v0.1.0",
            Translator("en")("plugin_name", version="0.1.0"),
        )
        self.assertEqual(
            "CoilForge 线圈工坊 v0.1.0",
            Translator("zh")("plugin_name", version="0.1.0"),
        )
        self.assertIn(
            "v0.1.0",
            Translator("zh")("window_title", version="0.1.0"),
        )


if __name__ == "__main__":
    unittest.main()

