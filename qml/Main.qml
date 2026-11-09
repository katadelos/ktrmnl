import QtQuick 2.15
import QtQuick.Window 2.15

// Rotation and dark colors are local to this window on every stock platform.
Window {
    id: root
    objectName: "ktrmnlWindow"
    visible: true
    visibility: Window.FullScreen
    width: runtimeDisplayWidth
    height: runtimeDisplayHeight
    color: ktrmnl.darkMode ? "#000000" : "#ffffff"
    title: "L:A_N:application_ID:org.ktrmnl_PC:N"
    flags: Qt.FramelessWindowHint

    property alias menuOpen: appView.menuOpen
    property alias menuPage: appView.menuPage
    property alias menuIndex: appView.menuIndex
    property bool keyboardVisible: appView.entryKeyboardVisible

    function openMenu(page) { appView.openMenu(page) }
    function closeMenu() { appView.closeMenu() }
    function handleAction(action) { appView.handleAction(action, false) }

    AppView {
        id: appView
        anchors.centerIn: parent
        width: ktrmnl.rotation % 180 === 0 ? root.width : root.height
        height: ktrmnl.rotation % 180 === 0 ? root.height : root.width
        rotation: ktrmnl.rotation
        controller: ktrmnl
        contentModel: content
        wifiBackend: wifi
        inputBackend: inputBridge
        translator: i18n
        paperColor: ktrmnl.darkMode ? "#000000" : "#ffffff"
        inkColor: ktrmnl.darkMode ? "#ffffff" : "#000000"
        textScale: runtimeTextScale
        rowHeightScale: runtimeRowHeightScale
        keyboardHeightRatio: runtimeKeyboardHeightRatio
        initialMenuOpen: runtimeInitialMenuOpen
        initialMenuPage: runtimeInitialMenuPage
    }

}
