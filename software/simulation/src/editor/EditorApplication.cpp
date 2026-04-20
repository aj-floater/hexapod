#include "EditorApplication.h"

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>

#include <imgui.h>
#include <imgui_internal.h>
#include <ImGuizmo.h>
#include <SDL_mouse.h>

#include <Magnum/GL/DefaultFramebuffer.h>
#include <Magnum/GL/Renderer.h>
#include <Magnum/ImGuiIntegration/Context.hpp>
#include <Magnum/ImGuiIntegration/Integration.h>
#include <Magnum/ImGuiIntegration/Widgets.h>
#include <Magnum/Math/Color.h>
#include <Magnum/Math/Functions.h>
#include <Magnum/Math/Time.h>

#include "MathUtils.h"

using namespace Magnum;
using namespace Magnum::Math::Literals;

namespace hexapod::simulation {

namespace {

const char* gizmoOperationLabel(const GizmoOperation operation) {
    switch(operation) {
        case GizmoOperation::Rotate: return "Rotate";
        case GizmoOperation::Translate:
        default: return "Translate";
    }
}

const char* gizmoSpaceLabel(const GizmoSpace space) {
    switch(space) {
        case GizmoSpace::World: return "World";
        case GizmoSpace::Local:
        default: return "Local";
    }
}

const char* primitiveKindLabel(const PrimitiveKind primitive) {
    switch(primitive) {
        case PrimitiveKind::Cylinder: return "Cylinder";
        case PrimitiveKind::Sphere: return "Sphere";
        case PrimitiveKind::Cube:
        default: return "Cube";
    }
}

Matrix4 matrixFromFloatArray(const float* values) {
    Matrix4 matrix;
    std::copy(values, values + 16, matrix.data());
    return matrix;
}

Transform transformFromMatrix(const Matrix4& matrix) {
    float matrixData[16];
    std::copy(matrix.data(), matrix.data() + 16, matrixData);

    float translation[3];
    float rotation[3];
    float scale[3];
    ImGuizmo::DecomposeMatrixToComponents(matrixData, translation, rotation, scale);

    return Transform{
        {translation[0], translation[1], translation[2]},
        {rotation[0], rotation[1], rotation[2]},
        {scale[0], scale[1], scale[2]}};
}

}

EditorApplication::EditorApplication(const Arguments& arguments):
    Platform::Sdl2Application{arguments, Configuration{}
        .setTitle("Hexapod Simulation")
        .setSize({1440, 900})
        .addWindowFlags(Configuration::WindowFlag::Resizable)},
    _editorStateDirectory{ensureEditorStateDirectory()},
    _imguiIniPath{_editorStateDirectory/"imgui.ini"},
    _prefsPath{_editorStateDirectory/"prefs.json"},
    _imguiIniPathString{_imguiIniPath.string()},
    _log{_editorStateDirectory/"log.txt"}
{
    _preferences = loadPreferences(_prefsPath, _log);

    _imgui = ImGuiIntegration::Context(
        Vector2{windowSize()}/dpiScaling(),
        windowSize(),
        framebufferSize());
    _imgui.connectApplicationClipboard(*this);
    _uiEventScale = (Vector2{windowSize()}/dpiScaling())/Vector2{windowSize()};

    ImGuiIO& io = ImGui::GetIO();
    io.ConfigFlags |= ImGuiConfigFlags_DockingEnable;
    io.IniFilename = _imguiIniPathString.c_str();

    applyTheme();

    GL::Renderer::enable(GL::Renderer::Feature::Blending);
    GL::Renderer::enable(GL::Renderer::Feature::ScissorTest);
    GL::Renderer::setBlendEquation(GL::Renderer::BlendEquation::Add,
        GL::Renderer::BlendEquation::Add);
    GL::Renderer::setBlendFunction(GL::Renderer::BlendFunction::SourceAlpha,
        GL::Renderer::BlendFunction::OneMinusSourceAlpha);

    setMinimalLoopPeriod(16.0_msec);
    _log.push("Editor shell initialized.");
}

EditorApplication::~EditorApplication() {
    saveState();
}

void EditorApplication::applyTheme() {
    ImGuiStyle& style = ImGui::GetStyle();
    style.WindowRounding = 6.0f;
    style.FrameRounding = 4.0f;
    style.TabRounding = 4.0f;
    style.ScrollbarRounding = 5.0f;
    style.WindowPadding = {10.0f, 8.0f};
    style.FramePadding = {8.0f, 5.0f};
    style.ItemSpacing = {8.0f, 6.0f};

    ImVec4* colors = style.Colors;
    colors[ImGuiCol_WindowBg] = ImVec4{0.09f, 0.10f, 0.12f, 1.00f};
    colors[ImGuiCol_MenuBarBg] = ImVec4{0.08f, 0.09f, 0.11f, 1.00f};
    colors[ImGuiCol_TitleBg] = ImVec4{0.11f, 0.13f, 0.17f, 1.00f};
    colors[ImGuiCol_TitleBgActive] = ImVec4{0.14f, 0.17f, 0.22f, 1.00f};
    colors[ImGuiCol_Header] = ImVec4{0.19f, 0.26f, 0.33f, 1.00f};
    colors[ImGuiCol_HeaderHovered] = ImVec4{0.24f, 0.34f, 0.43f, 1.00f};
    colors[ImGuiCol_HeaderActive] = ImVec4{0.29f, 0.40f, 0.50f, 1.00f};
    colors[ImGuiCol_Tab] = ImVec4{0.11f, 0.14f, 0.19f, 1.00f};
    colors[ImGuiCol_TabActive] = ImVec4{0.18f, 0.25f, 0.32f, 1.00f};
    colors[ImGuiCol_TabHovered] = ImVec4{0.22f, 0.31f, 0.39f, 1.00f};
    colors[ImGuiCol_Button] = ImVec4{0.16f, 0.21f, 0.27f, 1.00f};
    colors[ImGuiCol_ButtonHovered] = ImVec4{0.22f, 0.30f, 0.37f, 1.00f};
    colors[ImGuiCol_ButtonActive] = ImVec4{0.27f, 0.37f, 0.45f, 1.00f};
    colors[ImGuiCol_FrameBg] = ImVec4{0.12f, 0.15f, 0.19f, 1.00f};
    colors[ImGuiCol_FrameBgHovered] = ImVec4{0.18f, 0.22f, 0.29f, 1.00f};
    colors[ImGuiCol_FrameBgActive] = ImVec4{0.21f, 0.29f, 0.37f, 1.00f};
    colors[ImGuiCol_DockingPreview] = ImVec4{0.35f, 0.55f, 0.73f, 0.55f};
    colors[ImGuiCol_CheckMark] = ImVec4{0.64f, 0.78f, 0.90f, 1.00f};
    colors[ImGuiCol_ResizeGrip] = ImVec4{0.23f, 0.31f, 0.39f, 1.00f};
    colors[ImGuiCol_ResizeGripHovered] = ImVec4{0.33f, 0.45f, 0.57f, 1.00f};
    colors[ImGuiCol_ResizeGripActive] = ImVec4{0.43f, 0.58f, 0.74f, 1.00f};
}

void EditorApplication::drawEvent() {
    GL::defaultFramebuffer.clear(GL::FramebufferClear::Color|GL::FramebufferClear::Depth);

    _imgui.newFrame();
    ImGuizmo::BeginFrame();
    _arcball.updateTransformation();

    if(ImGui::GetIO().WantTextInput && !isTextInputActive())
        startTextInput();
    else if(!ImGui::GetIO().WantTextInput && isTextInputActive())
        stopTextInput();

    drawDockSpace();
    drawMenuBar();
    drawHierarchyPanel();
    drawInspectorPanel();
    drawLogPanel();
    drawViewportPanel();

    if(_preferences.showDemoWindow)
        ImGui::ShowDemoWindow(&_preferences.showDemoWindow);

    _imgui.updateApplicationCursor(*this);

    GL::Renderer::enable(GL::Renderer::Feature::Blending);
    GL::Renderer::enable(GL::Renderer::Feature::ScissorTest);
    GL::Renderer::disable(GL::Renderer::Feature::DepthTest);
    GL::Renderer::disable(GL::Renderer::Feature::FaceCulling);
    _imgui.drawFrame();

    swapBuffers();
    redraw();
}

void EditorApplication::viewportEvent(ViewportEvent& event) {
    GL::defaultFramebuffer.setViewport({{}, event.framebufferSize()});
    _imgui.relayout(Vector2{event.windowSize()}/event.dpiScaling(),
        event.windowSize(),
        event.framebufferSize());
    _uiEventScale = (Vector2{event.windowSize()}/event.dpiScaling())/Vector2{event.windowSize()};
    _layoutState.defaultLayoutPending = true;
}

void EditorApplication::keyPressEvent(KeyEvent& event) {
    if(_imgui.handleKeyPressEvent(event)) return;

    if(event.key() == Key::F) {
        frameSelectedEntity();
        event.setAccepted();
        return;
    }

    if(event.key() == Key::Home) {
        frameVisibleScene();
        event.setAccepted();
        return;
    }

    if(event.key() == Key::W) {
        _selection.operation = GizmoOperation::Translate;
        event.setAccepted();
        return;
    }

    if(event.key() == Key::E) {
        _selection.operation = GizmoOperation::Rotate;
        event.setAccepted();
        return;
    }

    if(event.key() == Key::Q) {
        _selection.space = _selection.space == GizmoSpace::Local ?
            GizmoSpace::World : GizmoSpace::Local;
        event.setAccepted();
        return;
    }
}

void EditorApplication::keyReleaseEvent(KeyEvent& event) {
    if(_imgui.handleKeyReleaseEvent(event)) return;
}

void EditorApplication::pointerPressEvent(PointerEvent& event) {
    const Vector2 uiPosition = uiPointerPosition(event.position());
    if(!ImGuizmo::IsUsing() &&
       !ImGuizmo::IsOver() &&
       beginViewportInteraction(event.pointer(), event.modifiers(), uiPosition)) {
        _imgui.handlePointerPressEvent(event);
        event.setAccepted();
        return;
    }

    const bool imguiHandled = _imgui.handlePointerPressEvent(event);
    if(imguiHandled) return;
}

void EditorApplication::pointerReleaseEvent(PointerEvent& event) {
    const Vector2 uiPosition = uiPointerPosition(event.position());
    if(!ImGuizmo::IsUsing() &&
       endViewportInteraction(uiPosition)) {
        _imgui.handlePointerReleaseEvent(event);
        event.setAccepted();
        return;
    }

    const bool imguiHandled = _imgui.handlePointerReleaseEvent(event);
    if(imguiHandled) return;
}

void EditorApplication::pointerMoveEvent(PointerMoveEvent& event) {
    const Vector2 uiPosition = uiPointerPosition(event.position());
    const Vector2 uiRelativePosition = uiPointerDelta(event.relativePosition());
    if(_viewportInteraction.active) {
        _imgui.handlePointerMoveEvent(event);
        if(ImGuizmo::IsUsing()) {
            cancelViewportInteraction();
            event.setAccepted();
            return;
        }

        if(updateViewportInteraction(uiPosition, uiRelativePosition, event.modifiers())) {
            event.setAccepted();
            return;
        }
    }

    const bool imguiHandled = _imgui.handlePointerMoveEvent(event);
    if(ImGuizmo::IsUsing()) {
        cancelViewportInteraction();
        event.setAccepted();
        return;
    }

    if(updateViewportInteraction(uiPosition, uiRelativePosition, event.modifiers())) {
        event.setAccepted();
        return;
    }

    if(imguiHandled) return;
}

void EditorApplication::scrollEvent(ScrollEvent& event) {
    const bool imguiHandled = _imgui.handleScrollEvent(event);
    if(!ImGuizmo::IsUsing() &&
       viewportContainsScreenPoint(uiPointerPosition(event.position()))) {
        const Float delta = event.offset().y();
        if(Math::abs(delta) >= 1.0e-2f)
            _arcball.zoom(delta);
        event.setAccepted();
        return;
    }

    if(imguiHandled) {
        event.setAccepted();
        return;
    }
}

void EditorApplication::textInputEvent(TextInputEvent& event) {
    if(_imgui.handleTextInputEvent(event)) return;
}

void EditorApplication::drawDockSpace() {
    ImGuiViewport* viewport = ImGui::GetMainViewport();
    ImGui::SetNextWindowPos(viewport->WorkPos);
    ImGui::SetNextWindowSize(viewport->WorkSize);
    ImGui::SetNextWindowViewport(viewport->ID);

    ImGuiWindowFlags flags = ImGuiWindowFlags_NoDocking|
        ImGuiWindowFlags_NoTitleBar|
        ImGuiWindowFlags_NoCollapse|
        ImGuiWindowFlags_NoResize|
        ImGuiWindowFlags_NoMove|
        ImGuiWindowFlags_NoBringToFrontOnFocus|
        ImGuiWindowFlags_NoNavFocus|
        ImGuiWindowFlags_MenuBar;

    ImGui::PushStyleVar(ImGuiStyleVar_WindowRounding, 0.0f);
    ImGui::PushStyleVar(ImGuiStyleVar_WindowBorderSize, 0.0f);
    ImGui::Begin("EditorRoot", nullptr, flags);
    ImGui::PopStyleVar(2);

    const ImGuiID dockspaceId = ImGui::GetID("SimulationDockSpace");
    ImGui::DockSpace(dockspaceId, ImVec2{0.0f, 0.0f}, ImGuiDockNodeFlags_None);
    ensureDefaultLayout();
    ImGui::End();
}

void EditorApplication::drawMenuBar() {
    if(!ImGui::BeginMainMenuBar()) return;

    if(ImGui::BeginMenu("View")) {
        ImGui::MenuItem("Hierarchy", nullptr, &_layoutState.panels.hierarchy);
        ImGui::MenuItem("Inspector", nullptr, &_layoutState.panels.inspector);
        ImGui::MenuItem("Log", nullptr, &_layoutState.panels.log);
        ImGui::MenuItem("ImGui Demo", nullptr, &_preferences.showDemoWindow);
        ImGui::EndMenu();
    }

    if(ImGui::BeginMenu("Layout")) {
        if(ImGui::MenuItem("Reset Layout"))
            resetLayout();
        if(ImGui::MenuItem("Reset Preferences"))
            resetPreferences();
        ImGui::EndMenu();
    }

    ImGui::Separator();
    ImGui::TextUnformatted("Magnum Sandbox");

    ImGui::EndMainMenuBar();
}

void EditorApplication::ensureDefaultLayout() {
    if(!_layoutState.defaultLayoutPending) return;
    if(std::filesystem::exists(_imguiIniPath)) {
        _layoutState.defaultLayoutPending = false;
        return;
    }

    const ImGuiID dockspaceId = ImGui::GetID("SimulationDockSpace");
    ImGui::DockBuilderRemoveNode(dockspaceId);
    ImGui::DockBuilderAddNode(dockspaceId, ImGuiDockNodeFlags_DockSpace);
    ImGui::DockBuilderSetNodeSize(dockspaceId, ImGui::GetMainViewport()->WorkSize);

    ImGuiID left = 0;
    ImGuiID right = 0;
    ImGuiID bottom = 0;
    ImGuiID center = dockspaceId;

    ImGui::DockBuilderSplitNode(center, ImGuiDir_Left, 0.20f, &left, &center);
    ImGui::DockBuilderSplitNode(center, ImGuiDir_Right, 0.25f, &right, &center);
    ImGui::DockBuilderSplitNode(center, ImGuiDir_Down, 0.26f, &bottom, &center);

    ImGui::DockBuilderDockWindow("Hierarchy", left);
    ImGui::DockBuilderDockWindow("Viewport", center);
    ImGui::DockBuilderDockWindow("Inspector", right);
    ImGui::DockBuilderDockWindow("Log", bottom);
    ImGui::DockBuilderFinish(dockspaceId);

    _layoutState.defaultLayoutPending = false;
}

void EditorApplication::drawHierarchyPanel() {
    if(!_layoutState.panels.hierarchy) return;
    if(!ImGui::Begin("Hierarchy", &_layoutState.panels.hierarchy)) {
        ImGui::End();
        return;
    }

    for(const SceneEntity& entity: _scene.entities()) {
        if(entity.parentId < 0)
            drawHierarchyNode(Magnum::Int(entity.id));
    }

    ImGui::End();
}

void EditorApplication::drawHierarchyNode(const Magnum::Int entityId) {
    SceneEntity* entity = _scene.findEntity(entityId);
    if(!entity) return;

    const std::vector<Magnum::Int> children = _scene.childIds(entityId);
    ImGuiTreeNodeFlags flags = ImGuiTreeNodeFlags_OpenOnArrow|
        ImGuiTreeNodeFlags_OpenOnDoubleClick|
        (children.empty() ? ImGuiTreeNodeFlags_Leaf : 0)|
        (_selection.selectedId == entityId ? ImGuiTreeNodeFlags_Selected : 0);

    const bool open = ImGui::TreeNodeEx(reinterpret_cast<void*>(std::intptr_t(entityId)), flags, "%s", entity->label.c_str());
    if(ImGui::IsItemClicked())
        setSelectedEntity(entityId);

    if(open) {
        for(const Magnum::Int childId: children)
            drawHierarchyNode(childId);
        ImGui::TreePop();
    }
}

void EditorApplication::drawInspectorPanel() {
    if(!_layoutState.panels.inspector) return;
    if(!ImGui::Begin("Inspector", &_layoutState.panels.inspector)) {
        ImGui::End();
        return;
    }

    if(SceneEntity* entity = _scene.findEntity(_selection.selectedId)) {
        char labelBuffer[128]{};
        std::snprintf(labelBuffer, sizeof(labelBuffer), "%s", entity->label.c_str());
        if(ImGui::InputText("Name", labelBuffer, sizeof(labelBuffer)))
            entity->label = labelBuffer;

        ImGui::Text("Primitive: %s", primitiveKindLabel(entity->primitive));
        ImGui::Checkbox("Visible", &entity->visible);

        float translation[3]{
            entity->localTransform.translation.x(),
            entity->localTransform.translation.y(),
            entity->localTransform.translation.z()};
        if(ImGui::DragFloat3("Translate", translation, 0.01f))
            entity->localTransform.translation = {translation[0], translation[1], translation[2]};

        float rotation[3]{
            entity->localTransform.rotationDegrees.x(),
            entity->localTransform.rotationDegrees.y(),
            entity->localTransform.rotationDegrees.z()};
        if(ImGui::DragFloat3("Rotate", rotation, 0.5f))
            entity->localTransform.rotationDegrees = {rotation[0], rotation[1], rotation[2]};

        float scale[3]{
            entity->localTransform.scale.x(),
            entity->localTransform.scale.y(),
            entity->localTransform.scale.z()};
        if(ImGui::DragFloat3("Scale", scale, 0.01f, 0.01f, 20.0f))
            entity->localTransform.scale = {scale[0], scale[1], scale[2]};

        ImGui::Separator();
    } else {
        ImGui::TextUnformatted("No entity selected.");
        ImGui::Separator();
    }

    ImGui::Text("Gizmo");
    if(ImGui::RadioButton("Translate", _selection.operation == GizmoOperation::Translate))
        _selection.operation = GizmoOperation::Translate;
    ImGui::SameLine();
    if(ImGui::RadioButton("Rotate", _selection.operation == GizmoOperation::Rotate))
        _selection.operation = GizmoOperation::Rotate;

    if(ImGui::RadioButton("Local", _selection.space == GizmoSpace::Local))
        _selection.space = GizmoSpace::Local;
    ImGui::SameLine();
    if(ImGui::RadioButton("World", _selection.space == GizmoSpace::World))
        _selection.space = GizmoSpace::World;

    ImGui::Separator();
    ImGui::Text("Snapping");
    ImGui::Checkbox("Translate Snap", &_preferences.translateSnapEnabled);
    float translateSnap[3]{
        _preferences.translateSnap.x(),
        _preferences.translateSnap.y(),
        _preferences.translateSnap.z()};
    if(ImGui::DragFloat3("Translate Step", translateSnap, 0.01f, 0.01f, 10.0f))
        _preferences.translateSnap = {translateSnap[0], translateSnap[1], translateSnap[2]};

    ImGui::Checkbox("Rotate Snap", &_preferences.rotateSnapEnabled);
    ImGui::DragFloat("Rotate Step", &_preferences.rotateSnapDegrees, 0.5f, 0.5f, 180.0f, "%.1f deg");

    ImGui::Separator();
    ImGui::Checkbox("Show Grid", &_preferences.showGrid);
    ImGui::Checkbox("Show Axes", &_preferences.showAxes);
    ImGui::Checkbox("Show Bounds", &_preferences.showBounds);

    ImGui::End();
}

void EditorApplication::drawLogPanel() {
    if(!_layoutState.panels.log) return;
    if(!ImGui::Begin("Log", &_layoutState.panels.log)) {
        ImGui::End();
        return;
    }

    if(ImGui::Button("Clear"))
        _log.clear();
    ImGui::Separator();

    for(const std::string& line: _log.lines())
        ImGui::TextUnformatted(line.c_str());

    if(ImGui::GetScrollY() >= ImGui::GetScrollMaxY())
        ImGui::SetScrollHereY(1.0f);

    ImGui::End();
}

void EditorApplication::drawViewportPanel() {
    if(!_viewport.open) return;
    if(!ImGui::Begin("Viewport", &_viewport.open, ImGuiWindowFlags_NoScrollbar)) {
        ImGui::End();
        return;
    }

    const ImVec2 available = ImGui::GetContentRegionAvail();
    _viewport.size = {Math::max(available.x, 1.0f), Math::max(available.y, 1.0f)};
    _viewport.origin = {ImGui::GetCursorScreenPos().x, ImGui::GetCursorScreenPos().y};
    _viewport.hovered = ImGui::IsWindowHovered(ImGuiHoveredFlags_AllowWhenBlockedByActiveItem);
    _viewport.focused = ImGui::IsWindowFocused();

    _viewportRenderer.ensureSize(Vector2i{Int(_viewport.size.x()), Int(_viewport.size.y())});
    _arcball.reshape(_viewportRenderer.size());
    _viewportRenderer.render(
        _scene,
        _selection,
        _arcball.viewMatrix(),
        viewportProjectionMatrix(),
        _preferences);

    ImGui::PushStyleVar(ImGuiStyleVar_FramePadding, ImVec2{0.0f, 0.0f});
    ImGuiIntegration::image(
        _viewportRenderer.colorTexture(),
        _viewport.size,
        {{0.0f, 1.0f}, {1.0f, 0.0f}});
    ImGui::PopStyleVar();
    _viewport.hovered = ImGui::IsItemHovered(ImGuiHoveredFlags_AllowWhenBlockedByActiveItem);
    _viewport.focused = ImGui::IsWindowFocused();

    drawViewportOverlay();
    ImGui::End();
}

void EditorApplication::drawViewportOverlay() {
    SceneEntity* entity = _scene.findEntity(_selection.selectedId);
    if(entity) {
        ImGuizmo::SetOrthographic(false);
        ImGuizmo::SetDrawlist();
        ImGuizmo::SetRect(_viewport.origin.x(), _viewport.origin.y(), _viewport.size.x(), _viewport.size.y());
        ImGuizmo::PushID(_selection.selectedId);

        const Matrix4 parentWorld = entity->parentId >= 0 ? _scene.worldTransform(entity->parentId) : Matrix4{Math::IdentityInit};
        const Matrix4 world = _scene.worldTransform(_selection.selectedId);

        float matrixData[16];
        std::copy(world.data(), world.data() + 16, matrixData);

        std::array<float, 3> translateSnap{
            _preferences.translateSnap.x(),
            _preferences.translateSnap.y(),
            _preferences.translateSnap.z()};
        std::array<float, 1> rotateSnap{_preferences.rotateSnapDegrees};

        const float* snap = nullptr;
        if(_selection.operation == GizmoOperation::Translate && _preferences.translateSnapEnabled)
            snap = translateSnap.data();
        else if(_selection.operation == GizmoOperation::Rotate && _preferences.rotateSnapEnabled)
            snap = rotateSnap.data();

        ImGuizmo::Manipulate(
            _viewportRenderer.viewMatrix().data(),
            _viewportRenderer.projectionMatrix().data(),
            _selection.operation == GizmoOperation::Translate ? ImGuizmo::TRANSLATE : ImGuizmo::ROTATE,
            _selection.space == GizmoSpace::Local ? ImGuizmo::LOCAL : ImGuizmo::WORLD,
            matrixData,
            nullptr,
            snap);

        if(ImGuizmo::IsUsing()) {
            const Matrix4 newWorld = matrixFromFloatArray(matrixData);
            const Matrix4 local = entity->parentId >= 0 ? parentWorld.inverted()*newWorld : newWorld;
            entity->localTransform = transformFromMatrix(local);
        }

        ImGuizmo::PopID();
    }

    ImGui::SetCursorScreenPos(ImVec2{_viewport.origin.x() + 12.0f, _viewport.origin.y() + 12.0f});
    ImGui::BeginChild("ViewportToolbar", ImVec2{500.0f, 82.0f}, true,
        ImGuiWindowFlags_NoScrollbar|
        ImGuiWindowFlags_NoScrollWithMouse|
        ImGuiWindowFlags_NoInputs|
        ImGuiWindowFlags_NoNav);
    if(entity)
        ImGui::Text("%s | %s", gizmoOperationLabel(_selection.operation), gizmoSpaceLabel(_selection.space));
    else
        ImGui::TextUnformatted("No selection");
    ImGui::SameLine();
    ImGui::Text("Distance %.2f", _arcball.viewDistance());
    ImGui::TextUnformatted("Drag orbit  Shift+drag or RMB drag pan  Wheel zoom");
    ImGui::TextUnformatted("LMB click select  Mouse capture during drag  F frame selection  Home frame scene");
    ImGui::EndChild();
}

void EditorApplication::resetLayout() {
    std::error_code error;
    std::filesystem::remove(_imguiIniPath, error);
    _layoutState.defaultLayoutPending = true;
    _log.push("Layout reset requested.");
}

void EditorApplication::resetPreferences() {
    _preferences = {};
    savePreferences(_prefsPath, _preferences);
    _log.push("Preferences reset to defaults.");
}

void EditorApplication::saveState() const {
    savePreferences(_prefsPath, _preferences);
}

void EditorApplication::setSelectedEntity(const Magnum::Int id) {
    _selection.selectedId = id;
    _log.push("Selection changed to entity " + std::to_string(id) + ".");
}

bool EditorApplication::beginViewportInteraction(const Pointer pointer,
                                                 const Modifiers modifiers,
                                                 const Magnum::Vector2& screenPosition) {
    if(!viewportContainsScreenPoint(screenPosition)) return false;
    if(pointer != Pointer::MouseLeft &&
       pointer != Pointer::MouseMiddle &&
       pointer != Pointer::MouseRight) return false;

    _viewportInteraction.active = true;
    _viewportInteraction.dragged = false;
    _viewportInteraction.selectionCandidate =
        pointer == Pointer::MouseLeft &&
        modifiers == Modifiers{};
    _viewportInteraction.pointer = pointer;
    _viewportInteraction.pressScreenPosition = screenPosition;
    _viewportInteraction.currentLocalPosition = viewportLocalPosition(screenPosition);
    _arcball.initTransformation(_viewportInteraction.currentLocalPosition);
    SDL_CaptureMouse(SDL_TRUE);
    return true;
}

bool EditorApplication::updateViewportInteraction(const Magnum::Vector2& screenPosition,
                                                  const Magnum::Vector2& relativePosition,
                                                  const Modifiers modifiers) {
    if(!_viewportInteraction.active) return false;

    const Magnum::Float dragDistance =
        (screenPosition - _viewportInteraction.pressScreenPosition).length();
    _viewportInteraction.dragged = _viewportInteraction.dragged || dragDistance >= 3.0f;
    if(!_viewportInteraction.dragged) return true;

    _viewportInteraction.currentLocalPosition += {relativePosition.x(), -relativePosition.y()};
    const Magnum::Vector2 localPosition = _viewportInteraction.currentLocalPosition;
    if(_viewportInteraction.pointer == Pointer::MouseRight ||
       (modifiers & Modifier::Shift))
        _arcball.translate(localPosition);
    else
        _arcball.rotate(localPosition);

    return true;
}

bool EditorApplication::endViewportInteraction(const Magnum::Vector2& screenPosition) {
    if(!_viewportInteraction.active) return false;

    const bool shouldSelect =
        _viewportInteraction.selectionCandidate &&
        !_viewportInteraction.dragged &&
        viewportContainsScreenPoint(screenPosition);
    cancelViewportInteraction();

    if(shouldSelect)
        handleViewportPick(screenPosition);
    return true;
}

void EditorApplication::cancelViewportInteraction() {
    if(_viewportInteraction.active)
        SDL_CaptureMouse(SDL_FALSE);
    _viewportInteraction = {};
}

void EditorApplication::handleViewportPick(const Magnum::Vector2& screenPosition) {
    const std::optional<SceneRayHit> hit = raycastViewportPoint(screenPosition);
    setSelectedEntity(hit ? hit->entityId : -1);
}

void EditorApplication::frameSelectedEntity() {
    if(_selection.selectedId < 0) return;
    frameCameraToBounds(_scene.worldBounds(_selection.selectedId), "selection");
}

void EditorApplication::frameVisibleScene() {
    const std::optional<Range3D> bounds = _scene.visibleBounds();
    if(!bounds) return;

    frameCameraToBounds(*bounds, "scene");
}

bool EditorApplication::viewportContainsScreenPoint(const Magnum::Vector2& position) const {
    if(!_viewport.open) return false;

    return position.x() >= _viewport.origin.x() &&
        position.y() >= _viewport.origin.y() &&
        position.x() <= _viewport.origin.x() + _viewport.size.x() &&
        position.y() <= _viewport.origin.y() + _viewport.size.y();
}

Magnum::Vector2 EditorApplication::viewportLocalPosition(const Magnum::Vector2& screenPosition) const {
    return screenPosition - _viewport.origin;
}

Magnum::Vector2 EditorApplication::uiPointerPosition(const Magnum::Vector2& windowPosition) const {
    return windowPosition*_uiEventScale;
}

Magnum::Vector2 EditorApplication::uiPointerDelta(const Magnum::Vector2& windowDelta) const {
    return windowDelta*_uiEventScale;
}

std::optional<SceneRayHit> EditorApplication::raycastViewportPoint(const Magnum::Vector2& screenPosition) const {
    if(_viewport.size.x() <= 0.0f || _viewport.size.y() <= 0.0f) return std::nullopt;

    const Vector2 local = viewportLocalPosition(screenPosition);
    if(local.x() < 0.0f || local.y() < 0.0f ||
       local.x() > _viewport.size.x() || local.y() > _viewport.size.y())
        return std::nullopt;

    const Ray3D ray = screenPointToRay(
        local,
        _viewport.size,
        _viewportRenderer.viewMatrix(),
        _viewportRenderer.projectionMatrix());
    return _scene.raycast(ray);
}

Magnum::Matrix4 EditorApplication::viewportProjectionMatrix() const {
    const Magnum::Float aspectRatio = Magnum::Float(_viewportRenderer.size().x())/
        Magnum::Float(_viewportRenderer.size().y());
    return Magnum::Matrix4::perspectiveProjection(
        _arcball.fov(),
        aspectRatio,
        0.01f,
        100.0f);
}

Magnum::Vector3 EditorApplication::cameraForward() const {
    return _arcball.transformationMatrix()
        .transformVector({0.0f, 0.0f, -1.0f})
        .normalized();
}

Magnum::Vector3 EditorApplication::cameraUp() const {
    return _arcball.transformationMatrix()
        .transformVector(Magnum::Vector3::yAxis())
        .normalized();
}

void EditorApplication::setCameraView(const Magnum::Vector3& center, const Magnum::Float distance) {
    const Magnum::Float clampedDistance = Math::clamp(distance, CameraMinDistance, CameraMaxDistance);
    const Magnum::Vector3 eye = center - cameraForward()*clampedDistance;
    _arcball.setViewParameters(eye, center, cameraUp());
}

void EditorApplication::frameCameraToBounds(const Magnum::Range3D& bounds, const char* const label) {
    const Vector3 center = bounds.center();
    const Float radius = (bounds.size()*0.5f).length();
    const Float aspectRatio = _viewport.size.y() > 0.0f ? _viewport.size.x()/_viewport.size.y() : 1.0f;

    setCameraView(center, framingDistanceForRadius(radius*1.15f, aspectRatio));
    _log.push(std::string{"Camera framed to "} + label + ".");
}

}
