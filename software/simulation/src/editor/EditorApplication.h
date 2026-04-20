#pragma once

#include <filesystem>
#include <optional>

#include <Magnum/ImGuiIntegration/Context.h>
#include <Magnum/Platform/Sdl2Application.h>

#include "ArcBall.h"
#include "MathUtils.h"
#include "Persistence.h"
#include "SceneModel.h"
#include "ViewportRenderer.h"

namespace hexapod::simulation {

class EditorApplication: public Magnum::Platform::Sdl2Application {
    public:
        explicit EditorApplication(const Arguments& arguments);
        ~EditorApplication();

    private:
        struct ViewportState {
            Magnum::Vector2 size{1.0f};
            Magnum::Vector2 origin{};
            bool hovered{false};
            bool focused{false};
            bool open{true};
        };

        struct ViewportInteractionState {
            bool active{false};
            bool dragged{false};
            bool selectionCandidate{false};
            Magnum::Platform::Sdl2Application::Pointer pointer{
                Magnum::Platform::Sdl2Application::Pointer::MouseLeft};
            Magnum::Vector2 pressScreenPosition{};
            Magnum::Vector2 currentLocalPosition{};
        };

        void drawEvent() override;
        void viewportEvent(ViewportEvent& event) override;
        void keyPressEvent(KeyEvent& event) override;
        void keyReleaseEvent(KeyEvent& event) override;
        void pointerPressEvent(PointerEvent& event) override;
        void pointerReleaseEvent(PointerEvent& event) override;
        void pointerMoveEvent(PointerMoveEvent& event) override;
        void scrollEvent(ScrollEvent& event) override;
        void textInputEvent(TextInputEvent& event) override;

        void applyTheme();
        void drawMenuBar();
        void drawDockSpace();
        void ensureDefaultLayout();
        void drawHierarchyPanel();
        void drawInspectorPanel();
        void drawLogPanel();
        void drawViewportPanel();
        void drawHierarchyNode(Magnum::Int entityId);
        void drawViewportOverlay();
        void resetLayout();
        void resetPreferences();
        void saveState() const;
        void setSelectedEntity(Magnum::Int id);
        bool beginViewportInteraction(Magnum::Platform::Sdl2Application::Pointer pointer,
                                      Magnum::Platform::Sdl2Application::Modifiers modifiers,
                                      const Magnum::Vector2& screenPosition);
        bool updateViewportInteraction(const Magnum::Vector2& screenPosition,
                                       const Magnum::Vector2& relativePosition,
                                       Magnum::Platform::Sdl2Application::Modifiers modifiers);
        bool endViewportInteraction(const Magnum::Vector2& screenPosition);
        void cancelViewportInteraction();
        void handleViewportPick(const Magnum::Vector2& screenPosition);
        void frameSelectedEntity();
        void frameVisibleScene();
        bool viewportContainsScreenPoint(const Magnum::Vector2& position) const;
        Magnum::Vector2 viewportLocalPosition(const Magnum::Vector2& screenPosition) const;
        Magnum::Vector2 uiPointerPosition(const Magnum::Vector2& windowPosition) const;
        Magnum::Vector2 uiPointerDelta(const Magnum::Vector2& windowDelta) const;
        std::optional<SceneRayHit> raycastViewportPoint(const Magnum::Vector2& screenPosition) const;
        Magnum::Matrix4 viewportProjectionMatrix() const;
        Magnum::Vector3 cameraForward() const;
        void setCameraView(const Magnum::Vector3& center, Magnum::Float distance);
        void frameCameraToBounds(const Magnum::Range3D& bounds, const char* label);

        std::filesystem::path _editorStateDirectory;
        std::filesystem::path _imguiIniPath;
        std::filesystem::path _prefsPath;
        std::string _imguiIniPathString;
        WorkspaceLayoutState _layoutState;
        EditorPreferences _preferences;
        SceneModel _scene;
        SelectionState _selection;
        ViewportRenderer _viewportRenderer;
        EditorLog _log;
        Magnum::ImGuiIntegration::Context _imgui{Magnum::NoCreate};
        ViewportState _viewport;
        Magnum::Vector2 _uiEventScale{1.0f};
        Magnum::Examples::ArcBall _arcball{
            {5.4f, 4.2f, 6.2f},
            {0.0f, 0.0f, 0.0f},
            -Magnum::Vector3::yAxis(),
            ViewportVerticalFov,
            {1, 1}};
        ViewportInteractionState _viewportInteraction;
};

}
