# AI Image Generation

## How do I generate an image?
Simply ask the assistant to create an image. For example: "Generate an image of an astronaut cat" or "Draw me a sunset over the ocean". The image appears as a card below the assistant's response. The administrator chooses the image model in the LLM settings; the qualities and sizes you can pick depend on that model.

## Can I edit a generated image?
Yes! After generating an image, you can ask the assistant to modify it. For example: "Make it more realistic" or "Add a hat to the cat". The assistant automatically uses your most recent image, generated or uploaded — you don't need to reference it explicitly. An uploaded photo can be edited the same way; the result keeps its proportions.

## How do I configure image quality and size?
Go to **Settings > Preferences > AI Image Generation**. You can choose a **Quality**, a **Size** (square, portrait or landscape, with its resolution — 1K or 2K when the model offers both) and a **Format** (PNG, JPEG or WebP) — the images LIA generates or edits for you are delivered in it: PNG keeps every pixel, JPEG and WebP are far lighter, and WebP keeps transparency. The qualities and sizes offered depend on the image model the administrator configured, and each quality shows its price range. If the administrator changes the model, a saved choice it does not offer is replaced by the closest one it does — never by a more expensive quality. Higher qualities and resolutions cost more and can take longer to generate.

## How much does image generation cost?
Cost depends on the image model the administrator configured, the quality and the size: the settings show each quality's price range per image. Editing an image can also bill the image it starts from, when the model prices it per image. Image generation costs are tracked and consolidated with text LLM costs in your usage summary; the debug panel gives each generation its own section (model, quality, size, image count, reference images, duration, cost) and positions it on the request timeline.

## Is there a limit to how many images I can generate?
Two safeguards apply. Your account's **usage limits** (cost caps per billing cycle, set by the administrator) cover image generation costs like any other cost. On top of that, a **technical rate limit** protects against runaway loops: by default, 10 image generations (and 10 edits) per 5 minutes per user. Normal use is unaffected; if the limit is reached, the assistant tells you how long to wait before trying again. The administrator can tune both the threshold and the window via the IMAGE_GENERATION_RATE_LIMIT_CALLS and IMAGE_GENERATION_RATE_LIMIT_WINDOW environment variables.

## Is the image generation feature enabled by default?
Yes, image generation is enabled by default for all users. The administrator can disable it globally via the IMAGE_GENERATION_ENABLED environment variable. Individual users can toggle it in Settings > Preferences.

## How do I download a generated image?
Three options: **(1)** Click the download button (arrow icon) that appears on hover over the image in the chat — on mobile, the button is always visible. **(2)** Open the full-screen lightbox by clicking the image, then use the download button in the top-right corner. **(3)** On mobile, long-press the image to trigger the native browser "Save Image" menu, just like on any other website.

## How long does a generated image stay available?

Not forever. A generated image is stored as an attachment with an expiry, and a
scheduled cleanup removes expired attachments every few hours. Each image card
now states the deadline it received from the server, and switches to an amber
tone in the final hours so you can download it in time.

The deadline always comes from the server rather than being written into the
interface: the retention window is configurable by the administrator, so a
duration hard-coded in the app would eventually be wrong. Images generated before
this was introduced simply say nothing rather than guess.

## Are my generated images saved?
Yes, images are saved as attachments on disk. They persist across page reloads and survive a conversation reset: you find them in **Settings › My generated files**, until the expiry each image card states — the images a connection shared with you included.

You can also ask LIA: "*show me the lighthouse image from this morning*" — it finds the image in your gallery and shows it again in the chat. And an image LIA generated for you can be shared with a connection from its card (see Peer Connections).

## Which image models can LIA use?
The one your administrator configured, from two families: OpenAI's **GPT Image** and **Qwen Image 3.0** (Alibaba Cloud). Both create an image and edit a photo you attach.

Each model declares what it can do — its qualities, its sizes, its resolutions — and LIA offers you only that. A model no family declares cannot be priced, offered or selected. If your saved preference does not exist on the configured model, LIA takes the nearest option it offers — the cheapest offered quality, the size of the same orientation and nearest area — and never a dearer one. The format you chose (PNG, JPEG or WebP) is applied to every image, whatever the provider.

The displayed cost counts everything the provider bills: the image, and the source image of an edit when the provider prices it per image (Qwen does; OpenAI bills it as tokens). An image that was billed but could not be delivered is still counted, because the provider charged it.

## What does the "Enhance prompts automatically" option do?
It lives in **Settings > Preferences > AI Image Generation** and is off by default. When it is on, before each new image a dedicated model rewrites your description following the advice the image provider publishes — framing, light, lens, style — without changing what you ask for.

**What is protected:** a text you put in quotes (a title, a sign) must come back unchanged in the rewritten version; otherwise, or when the rewrite fails, exceeds the allowed length or comes back empty, your original description is sent. The option therefore never blocks an image.

**What it leaves alone:** editing a photo keeps your request as is, and your gallery shows your own words. The rewrite is one short extra call, counted in your usage like everything else; your administrator can also withdraw the option for the whole instance.
