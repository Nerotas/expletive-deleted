# Summary

The initial UI has been created. This guide catalogs and summarizes changes and improvements.

## Critical Fixes: Profane Words
- Profane words are currently not editable by users from the frontend.
- Discovered (potentially profane) words are not visible in the UI.

## File Management
The "processed" folder was originally meant as a workflow status to indicate that a file had been processed. Now that we have a visible status, it should have a new purpose: removing files from the queue.

Once a file is done being transcoded, we need a button to archive it for cleanliness. This is a QOL feature that allows users to keep their queue clean. We can add a setting to allow users to automatically handle archiving, but it should default to off.

## Whisper Model
"large-v3" is currently the only model that works consistently. However, we should ultimately provide the user with that choice. We should default to "large-v3" but allow users to select another model. There needs to be a notice that quality and accuracy drop noticeably with each smaller model.

## Whisper Library
As noted above, Whisper with large-v3 is the best option and the only one that provides consistently accurate results. However, faster-whisper is also a viable option. Like with the models, the original Whisper library is more accurate, but much slower. This should be an informed user choice.

## Color Scheme
The beige colors are okay, but I much prefer a light blue scheme to give the app more personality. The presumed audience is movie-savvy or otherwise a media enthusiast. Blue/orange is a common action-cinema color scheme that we can draw from.

Future options: horror theme, comedy theme, etc.

## Icon
We need a unique icon/favicon.ico, but we can start with the Prohibited Sign (🛇, U+1F6C7). Ultimately, it would be nice to use symbols ($%!) behind it to indicate the app's primary function.

## About

The About section needs to be expanded into a dedicated popup page. It should provide users with information about the application, its purpose, licensing, and user responsibilities.

The page should include:

- A brief description of the application and its purpose.
- Information about user responsibilities, including any software or dependencies the user is required to install separately.
- A note explaining that packages such as FFmpeg are not bundled with the application and must be installed by the user due to their licensing and distribution requirements.
- Links to the project's repository.
- A link to the developer's GitHub profile.
- Appropriate license and third-party software information.
- A link to the project's Ko-fi page for users who wish to support development.

### Ko-fi

Research indicates that linking to a specific Ko-fi Creator Page from the application should be permissible. Ko-fi's current terms allow links to Creator Pages, although their linking rules and content policies should be reviewed before implementation.

The Ko-fi link should be a standard external link rather than embedding or framing the Ko-fi page within the application.