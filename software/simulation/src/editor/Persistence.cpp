#include "Persistence.h"

#include <system_error>
#include <fstream>
#include <optional>
#include <regex>
#include <sstream>

namespace hexapod::simulation {

namespace {

std::optional<bool> parseBool(const std::string& input, const std::string& key) {
    const std::regex pattern{"\"" + key + "\"\\s*:\\s*(true|false)"};
    std::smatch match;
    if(!std::regex_search(input, match, pattern)) return std::nullopt;
    return match[1] == "true";
}

std::optional<Magnum::Float> parseFloat(const std::string& input, const std::string& key) {
    const std::regex pattern{"\"" + key + "\"\\s*:\\s*(-?[0-9]+(?:\\.[0-9]+)?)"};
    std::smatch match;
    if(!std::regex_search(input, match, pattern)) return std::nullopt;
    return Magnum::Float(std::stof(match[1]));
}

std::optional<Magnum::Vector3> parseVector3(const std::string& input, const std::string& key) {
    const std::regex pattern{
        "\"" + key + "\"\\s*:\\s*\\[\\s*(-?[0-9]+(?:\\.[0-9]+)?)\\s*,\\s*(-?[0-9]+(?:\\.[0-9]+)?)\\s*,\\s*(-?[0-9]+(?:\\.[0-9]+)?)\\s*\\]"};
    std::smatch match;
    if(!std::regex_search(input, match, pattern)) return std::nullopt;
    return Magnum::Vector3{
        Magnum::Float(std::stof(match[1])),
        Magnum::Float(std::stof(match[2])),
        Magnum::Float(std::stof(match[3]))};
}

}

EditorLog::EditorLog(std::filesystem::path outputPath):
    _outputPath{std::move(outputPath)} {}

void EditorLog::push(std::string message) {
    _lines.push_back(message);

    if(_outputPath.empty()) return;
    std::ofstream output{_outputPath, std::ios::app};
    if(output) output << message << '\n';
}

void EditorLog::clear() {
    _lines.clear();
    if(!_outputPath.empty()) {
        std::ofstream output{_outputPath, std::ios::trunc};
        static_cast<void>(output);
    }
}

std::filesystem::path ensureEditorStateDirectory() {
    const std::filesystem::path cwd = std::filesystem::current_path();
    const std::filesystem::path codexPath = cwd/".codex";
    const std::filesystem::path primary = codexPath/"editor";
    const std::filesystem::path fallback = cwd/".simulation-state"/"editor";

    std::error_code error;
    if(!std::filesystem::exists(codexPath, error) || std::filesystem::is_directory(codexPath, error)) {
        std::filesystem::create_directories(primary, error);
        if(!error) return primary;
    }

    error.clear();
    std::filesystem::create_directories(fallback, error);
    if(!error) return fallback;

    return cwd;
}

EditorPreferences loadPreferences(const std::filesystem::path& path, EditorLog& log) {
    EditorPreferences preferences;
    if(!std::filesystem::exists(path)) {
        log.push("Preferences: no existing prefs.json, using defaults.");
        return preferences;
    }

    std::ifstream input{path};
    if(!input) {
        log.push("Preferences: failed to open prefs.json, using defaults.");
        return preferences;
    }

    std::stringstream buffer;
    buffer << input.rdbuf();
    const std::string contents = buffer.str();

    if(const auto value = parseBool(contents, "translateSnapEnabled")) preferences.translateSnapEnabled = *value;
    if(const auto value = parseVector3(contents, "translateSnap")) preferences.translateSnap = *value;
    if(const auto value = parseBool(contents, "rotateSnapEnabled")) preferences.rotateSnapEnabled = *value;
    if(const auto value = parseFloat(contents, "rotateSnapDegrees")) preferences.rotateSnapDegrees = *value;
    if(const auto value = parseBool(contents, "showGrid")) preferences.showGrid = *value;
    if(const auto value = parseBool(contents, "showBounds")) preferences.showBounds = *value;
    if(const auto value = parseBool(contents, "showAxes")) preferences.showAxes = *value;
    if(const auto value = parseBool(contents, "showDemoWindow")) preferences.showDemoWindow = *value;

    log.push("Preferences: loaded prefs.json.");
    return preferences;
}

void savePreferences(const std::filesystem::path& path, const EditorPreferences& preferences) {
    std::ofstream output{path, std::ios::trunc};
    if(!output) return;

    output
        << "{\n"
        << "  \"translateSnapEnabled\": " << (preferences.translateSnapEnabled ? "true" : "false") << ",\n"
        << "  \"translateSnap\": [" << preferences.translateSnap.x() << ", " << preferences.translateSnap.y() << ", " << preferences.translateSnap.z() << "],\n"
        << "  \"rotateSnapEnabled\": " << (preferences.rotateSnapEnabled ? "true" : "false") << ",\n"
        << "  \"rotateSnapDegrees\": " << preferences.rotateSnapDegrees << ",\n"
        << "  \"showGrid\": " << (preferences.showGrid ? "true" : "false") << ",\n"
        << "  \"showBounds\": " << (preferences.showBounds ? "true" : "false") << ",\n"
        << "  \"showAxes\": " << (preferences.showAxes ? "true" : "false") << ",\n"
        << "  \"showDemoWindow\": " << (preferences.showDemoWindow ? "true" : "false") << "\n"
        << "}\n";
}

}
