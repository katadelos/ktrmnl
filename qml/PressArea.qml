import QtQuick 2.15

MouseArea {
    id: root
    property var theme
    property var actionData
    enum Feedback { Idle, Pressed, Settled, Released }
    property int feedbackState: PressArea.Idle
    readonly property bool highlighted: feedbackState !== PressArea.Idle
    property var pendingData
    signal triggered(var data)

    function cancelFeedback() {
        feedback.stop()
        feedbackState = PressArea.Idle
        pendingData = undefined
    }

    function deliver() {
        var data = pendingData
        cancelFeedback()
        triggered(data)
    }

    onPressed: {
        if (feedbackState !== PressArea.Idle) {
            mouse.accepted = false
            return
        }
        theme.inputMode = Theme.Touch
        // Preserve the pressed target if a Wi-Fi scan reorders the list.
        pendingData = actionData
        feedbackState = PressArea.Pressed
        feedback.restart()
    }
    onClicked: {
        if (feedbackState === PressArea.Pressed) feedbackState = PressArea.Released
        else if (feedbackState === PressArea.Settled) deliver()
    }
    onReleased: {
        if (mouse.x < 0 || mouse.y < 0 || mouse.x >= width || mouse.y >= height)
            cancelFeedback()
    }
    onCanceled: cancelFeedback()
    onVisibleChanged: if (!visible) cancelFeedback()
    onEnabledChanged: if (!enabled) cancelFeedback()

    Timer {
        id: feedback
        // Let a short tap reach the e-ink display before changing the page.
        interval: 150
        onTriggered: {
            if (root.feedbackState === PressArea.Released) root.deliver()
            else if (root.feedbackState === PressArea.Pressed)
                root.feedbackState = PressArea.Settled
        }
    }
}
