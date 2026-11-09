import QtQuick 2.15

Rectangle {
    id: root
    objectName: "contentView"
    property var theme
    property var translator
    property string imageSource: ""
    property int imageRevision: 0
    property string imagePresentation: "aspect_fit"
    property bool hasContent: false
    property bool busy: false
    property string presentationState: "ready"
    property string statusText: ""
    property string contentMode: "trmnl"
    property bool wifiConnected: true
    enum RecoveryAction { Secondary, Primary }
    property int selectedAction: ContentView.Primary
    readonly property bool localImages: contentMode === "local_images"
    readonly property bool wifiDisconnected: !localImages && !wifiConnected
    readonly property bool recoveryVisible: presentationState === "empty"
                                             || presentationState === "offline"
                                             || presentationState === "error"
    readonly property string primaryAction: wifiDisconnected ? "wifi"
        : localImages ? "folder"
        : (presentationState === "offline" || presentationState === "error") ? "retry"
        : "content"
    readonly property string secondaryAction: wifiDisconnected ? "content"
        : localImages ? "retry"
        : primaryAction === "retry" ? "content" : ""
    readonly property string activeLanguage: translator
        ? String(translator.language) : "en"
    signal menuRequested()
    signal contentSettingsRequested()
    signal imageFolderRequested()
    signal wifiSettingsRequested()
    signal retryRequested()

    color: theme.paper

    function translatedText(key) {
        var language = activeLanguage
        return translator.text(String(key))
    }

    function stateTitle() {
        if (presentationState === "loading") return translatedText("content.loading")
        if (recoveryVisible && wifiDisconnected) return translatedText("content.wifi_disconnected")
        if (presentationState === "empty") {
            if (localImages) return translatedText("content.no_images")
            if (contentMode === "http_push") return translatedText("content.waiting_image")
            return translatedText("content.empty")
        }
        if (presentationState === "offline") return translatedText("content.server_unavailable")
        if (presentationState === "error") return translatedText("content.error")
        return translatedText("content.ready")
    }

    function stateMessage() {
        if (presentationState === "loading") return translatedText("content.loading_message")
        if (recoveryVisible && wifiDisconnected) return translatedText("content.wifi_disconnected_message")
        if (presentationState === "offline") return translatedText("content.server_unavailable_message")
        if (presentationState === "empty") {
            if (localImages) return translatedText("content.no_images_message")
            if (contentMode === "http_push") return translatedText("content.waiting_image_message")
            return translatedText("content.setup_message")
        }
        if (presentationState === "error")
            return translatedText(localImages ? "content.local_error_message" : "content.error_message")
        return statusText
    }

    function stateDetail() {
        if (wifiDisconnected || (presentationState !== "offline" && presentationState !== "error"))
            return ""
        var detail = statusText.trim()
        if (detail === "TRMNL server not available." || detail === "Server unavailable.")
            return ""
        return detail.replace(/^(Display offline|Display error|Local image error|TRMNL server check failed|Push error):\s*/, "")
    }

    function actionLabel(action) {
        if (action === "wifi") return translatedText("content.wifi_settings")
        if (action === "folder") return translatedText("content.choose_folder")
        if (action === "retry") return translatedText("action.retry")
        return translatedText("content.open_settings")
    }

    function recover(action) {
        if (action === "wifi") wifiSettingsRequested()
        else if (action === "folder") imageFolderRequested()
        else if (action === "retry") retryRequested()
        else contentSettingsRequested()
    }

    function handleAction(action) {
        if (displayImage.visible) return false
        if (action === "left" || action === "up") selectedAction = ContentView.Secondary
        else if (action === "right" || action === "down") selectedAction = ContentView.Primary
        else if (action === "select") {
            if (!recoveryVisible) contentSettingsRequested()
            else {
                var target = selectedAction === ContentView.Secondary && secondaryAction.length > 0
                    ? secondaryAction : primaryAction
                if (target !== "retry" || !busy) recover(target)
            }
        } else return false
        return true
    }

    // Keep the background tap target behind the recovery controls.
    MouseArea {
        anchors.fill: parent
        onClicked: root.menuRequested()
    }

    Image {
        id: displayImage
        objectName: "displayImage"
        anchors.fill: parent
        visible: root.hasContent && root.imageSource.length > 0
        source: visible
                ? root.imageSource
                  + (root.imageSource.indexOf("?") >= 0 ? "&" : "?")
                  + "revision=" + root.imageRevision
                : ""
        cache: false
        asynchronous: false
        smooth: false
        mipmap: false
        fillMode: root.imagePresentation === "pixel_exact"
                  ? Image.Pad : Image.PreserveAspectFit
    }

    Column {
        anchors.centerIn: parent
        width: Math.min(parent.width - 2 * root.theme.outerMargin, 650 * root.theme.scale)
        spacing: Math.round(14 * root.theme.scale)
        visible: !displayImage.visible

        Text {
            width: parent.width
            text: root.stateTitle()
            color: root.theme.ink
            font.family: root.theme.displayFont
            font.pixelSize: root.theme.titleSize
            font.bold: true
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignLeft
        }

        Rectangle {
            width: parent.width
            height: root.theme.divider
            color: root.theme.ink
        }

        Text {
            width: parent.width
            text: root.stateMessage()
            color: root.theme.ink
            font.family: root.theme.bodyFont
            font.pixelSize: root.theme.dialogBodySize
            wrapMode: Text.Wrap
            lineHeight: 1.15
            horizontalAlignment: Text.AlignLeft
        }

        Text {
            width: parent.width
            text: root.stateDetail()
            visible: text.length > 0
            color: root.theme.ink
            font.family: root.theme.bodyFont
            font.pixelSize: root.theme.hintSize
            wrapMode: Text.Wrap
            maximumLineCount: 3
            elide: Text.ElideRight
            horizontalAlignment: Text.AlignLeft
        }

        ActionButtonRow {
            visible: root.recoveryVisible && root.secondaryAction.length > 0
            width: parent.width
            theme: root.theme
            leftText: root.actionLabel(root.secondaryAction)
            rightText: root.actionLabel(root.primaryAction)
            rightEnabled: root.primaryAction !== "retry" || !root.busy
            leftEnabled: root.secondaryAction !== "retry" || !root.busy
            leftSelected: root.selectedAction === ContentView.Secondary
            rightSelected: root.selectedAction === ContentView.Primary
            onLeftRequested: root.recover(root.secondaryAction)
            onRightRequested: root.recover(root.primaryAction)
        }

        ActionButton {
            visible: root.recoveryVisible && root.secondaryAction.length === 0
            width: parent.width
            height: root.theme.rowHeight
            theme: root.theme
            text: root.actionLabel(root.primaryAction)
            primary: true
            selected: true
            enabled: root.primaryAction !== "retry" || !root.busy
            onRequested: root.recover(root.primaryAction)
        }

        ActionButton {
            visible: !root.recoveryVisible
            width: parent.width
            height: root.theme.rowHeight
            theme: root.theme
            text: root.translatedText("content.open_settings")
            selected: true
            onRequested: root.contentSettingsRequested()
        }
    }
}
