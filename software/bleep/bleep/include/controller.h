#ifndef controller_h
#define controller_h

#include <Magnum/Platform/Sdl2Application.h>
#include <Magnum/Math/Vector2.h>
#include <SDL.h>

#if __APPLE__
#include <IOKit/hid/IOHIDLib.h>
#include <CoreFoundation/CoreFoundation.h>
#include <stdio.h>
#include <stdlib.h>

static void activate_gamepad(__IOHIDDevice *device) {
  IOReturn r = IOHIDDeviceOpen(device, kIOHIDOptionsTypeNone);
  if (r != kIOReturnSuccess) {
    printf("  Failed to open device - %d\n", r);
    return;
  }
  uint8_t controlBlob[] = { 0x42, 0x0C, 0x00, 0x00};
  IOHIDDeviceSetReport(device, kIOHIDReportTypeFeature, 0xF4, controlBlob, sizeof(controlBlob));

  printf("  Activating device...\n");
  sleep(1);

  uint8_t rumbleBlob[] = {
    0x01,
    0x00,
    0x00,
    0x00,
    0x00,
    0x00, // rumble values [0x00, right-timeout, right-force, left-timeout, left-force]
    0x00,
    0x00, // Gyro
    0x00,
    0x00,
    0x00, // 0x02=LED1 .. 0x10=LED4
    /*
     * the total time the led is active (0xff means forever)
     * |     duty_length: how long a cycle is in deciseconds:
     * |     |                              (0 means "blink very fast")
     * |     |     ??? (Maybe a phase shift or duty_length multiplier?)
     * |     |     |     % of duty_length led is off (0xff means 100%)
     * |     |     |     |     % of duty_length led is on (0xff is 100%)
     * |     |     |     |     |
     * 0xff, 0x27, 0x10, 0x00, 0x32,
     */
    0xff,
    0x27,
    0x10,
    0x00,
    0x32, // LED 4
    0xff,
    0x27,
    0x10,
    0x00,
    0x32, // LED 3
    0xff,
    0x27,
    0x10,
    0x00,
    0x32, // LED 2
    0xff,
    0x27,
    0x10,
    0x00,
    0x32, // LED 1
    0x00,
    0x00,
    0x00,
    0x00,
    0x00,
    // Necessary for Fake DS3
    0x00,
    0x00,
    0x00,
    0x00,
    0x00,
    0x00,
    0x00,
    0x00,
    0x00,
    0x00,
    0x00,
    0x00,
    0x00,
  };
  static const size_t RumbleLengthL = 4;
  static const size_t RumblePowerL = 5;
  static const size_t RumbleLengthR = 2;
  static const size_t RumblePowerR = 3;
  rumbleBlob[RumbleLengthL] = rumbleBlob[RumbleLengthR] = 20;
  rumbleBlob[RumblePowerL]                              = 150;
  rumbleBlob[RumblePowerR]                              = 1;
  IOHIDDeviceSetReport(device, kIOHIDReportTypeOutput, 1, rumbleBlob, sizeof(rumbleBlob));
  IOHIDDeviceClose(device, kIOHIDOptionsTypeNone);
  printf("  Should be rumbling!\n");
}

void init_gamepad() {
  static const SInt32 VendorId = 0x054C;
  static const SInt32 ProductId = 0x0268;

  CFNumberRef vendorIdNum = CFNumberCreate(kCFAllocatorDefault, kCFNumberSInt32Type, &VendorId);
  CFNumberRef productIdNum = CFNumberCreate(kCFAllocatorDefault, kCFNumberSInt32Type, &ProductId);
  
  const void *keys[2] = {
    CFSTR(kIOHIDVendorIDKey),
    CFSTR(kIOHIDProductIDKey),
  };

  const void *values[2] = {
    vendorIdNum,
    productIdNum
  };

  IOHIDManagerRef manager = IOHIDManagerCreate(kCFAllocatorDefault, kIOHIDOptionsTypeNone);  
  CFDictionaryRef matching = CFDictionaryCreate(NULL, keys, values, 2, NULL, NULL);
  IOHIDManagerSetDeviceMatching(manager, matching);

  CFSetRef deviceSet = IOHIDManagerCopyDevices(manager);
  if (deviceSet != NULL) {
    CFIndex count = CFSetGetCount(deviceSet);
    if (count > 0) {
      printf("Discovered %ld DualShock 3 gamepads\n", count);
      __IOHIDDevice **gamepads = (__IOHIDDevice **)calloc(count, sizeof(__IOHIDDevice *));
      CFSetGetValues(deviceSet, (const void **)gamepads);
      for (CFIndex i = 0; i < count; i++) {
        printf("Handling device %ld:\n", i);
        activate_gamepad(gamepads[i]);
      }
      free(gamepads);
    } else {
      printf("No DualShock 3 gamepads found!\n");
    }
    CFRelease(deviceSet);
  }
  CFRelease(productIdNum);
  CFRelease(vendorIdNum);
  CFRelease(matching);
  CFRelease(manager);
}

#endif

using namespace Magnum;

class Controller {
public:
  Controller() : leftJoystick{0.0f}, rightJoystick{0.0f} {}

  void DrawJoystick(float x, float y, ImVec2 position, float radius) {
    if (isnan(x)) x = 0;
    if (isnan(y)) y = 0;

    // Draw the outer circle of the joystick
    ImGui::GetWindowDrawList()->AddCircleFilled(position, radius, ImGui::GetColorU32(ImGuiCol_Button), 12);

    // Calculate the position of the inner circle based on the joystick's input
    ImVec2 joystickPos(position.x + (x * radius * 0.6), position.y + (y * radius * 0.6));

    // Draw the inner circle of the joystick
    ImGui::GetWindowDrawList()->AddCircleFilled(joystickPos, radius * 0.6f, ImGui::GetColorU32(ImGuiCol_ButtonActive), 12);
}

  void showGUI(){
    ImGui::Begin("Joystick Controller");

    ImVec2 position = ImVec2(ImGui::GetWindowPos().x + ImGui::GetWindowWidth()/2 - 50, ImGui::GetWindowPos().y + ImGui::GetWindowHeight()/2);
    DrawJoystick(leftJoystick.x(), leftJoystick.y(), position, 40);

    position = ImVec2(ImGui::GetWindowPos().x + ImGui::GetWindowWidth()/2 + 50, ImGui::GetWindowPos().y + ImGui::GetWindowHeight()/2);
    DrawJoystick(rightJoystick.x(), rightJoystick.y(), position, 40);
    
    ImGui::InvisibleButton("Spacer", ImVec2(1.0f, 100.0f)); // Creates 50px horizontal and 20px vertical space

    if (ImGui::Button("Search...")){
      init_gamepad();
    };

    ImGui::End();
  }

  SDL_Joystick *joystick0;
  SDL_Joystick *joystick1;
  void init(){

    // remember to add SDL_INIT_JOYSTICK to SDL_Init() in magnum
    printf("%i joysticks were found.\n\n", SDL_NumJoysticks() );

    SDL_JoystickEventState(SDL_ENABLE);
    joystick0 = SDL_JoystickOpen(0);
    joystick1 = SDL_JoystickOpen(1);
  }

  void update(){
    // leftJoystick = leftMovement.normalized();
    // rightJoystick = rightMovement.normalized();

    // if (isnan(leftJoystick.x())) leftJoystick.x() = 0;
    // if (isnan(leftJoystick.y())) leftJoystick.y() = 0;
    // if (isnan(rightJoystick.x())) rightJoystick.x() = 0;
    // if (isnan(rightJoystick.y())) rightJoystick.y() = 0;
  }

  float GetLeftJoystickScalar() {
    return sqrt(pow(leftJoystick.x(), 2) + pow(leftJoystick.y(), 2));
  }
  float GetRightJoystickScalar() {
    return sqrt(pow(rightJoystick.x(), 2) + pow(rightJoystick.y(), 2));
  }

  bool CheckIfJoysticksCentered(){
    // Checks if both joysticks are centered (or close enough to be considered centered)
    if (abs(leftJoystick.x()) <= 0.1 && abs(leftJoystick.y()) <= 0.1 && abs(rightJoystick.x()) <= 0.1 && abs(rightJoystick.y()) <= 0.1){
      return true;
    } 
    else return false;
  }

  Vector2 leftJoystick;
  Vector2 rightJoystick;
  Vector2 leftMovement;
  Vector2 rightMovement;

  bool centered = false;

  bool leftbutton;
  bool rightbutton;
};

#endif