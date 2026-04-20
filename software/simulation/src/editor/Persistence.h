#pragma once

#include <filesystem>
#include <string>
#include <vector>

#include "EditorTypes.h"

namespace hexapod::simulation {

class EditorLog {
    public:
        explicit EditorLog(std::filesystem::path outputPath = {});

        void push(std::string message);

        const std::vector<std::string>& lines() const { return _lines; }
        void clear();

    private:
        std::filesystem::path _outputPath;
        std::vector<std::string> _lines;
};

std::filesystem::path ensureEditorStateDirectory();
EditorPreferences loadPreferences(const std::filesystem::path& path, EditorLog& log);
void savePreferences(const std::filesystem::path& path, const EditorPreferences& preferences);

}
