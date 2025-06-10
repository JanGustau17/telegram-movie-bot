
````markdown
# Telegram Movie Bot

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/YOUR_GITHUB_USERNAME/your-bot-repo-name)

A Telegram bot designed to help users find and retrieve movie files by code or name. Admins can easily add, update, and delete movie entries in a Firebase Realtime Database.

---

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Local Setup](#local-setup)
  - [Environment Variables](#environment-variables)
  - [Running Locally](#running-locally)
- [Firebase Realtime Database Setup](#firebase-realtime-database-setup)
- [Deployment to Heroku](#deployment-to-heroku)
  - [Heroku CLI Installation](#heroku-cli-installation)
  - [Creating a Heroku App](#creating-a-heroku-app)
  - [Setting Heroku Config Vars](#setting-heroku-config-vars)
  - [Deploying Your Bot](#deploying-your-bot)
  - [Procfile Explained](#procfile-explained)
- [Bot Usage](#bot-usage)
- [Admin Commands](#admin-commands)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)
- [Contact](#contact)

---

## Features

* **Movie Retrieval:** Users can request movies by a unique code or by searching for a movie name.
* **Firebase Integration:** All movie data (file ID, name, code) is stored and managed using Firebase Realtime Database.
* **Admin Panel:** Dedicated commands for authorized administrators to:
    * Add new movies with file uploads, custom codes, and names.
    * Delete existing movies by their code.
    * List all available movies and their codes.
* **User Statistics:** Tracks unique users interacting with the bot.
* **User-Friendly Keyboard:** Provides convenient buttons for common actions like listing movies and getting help.

---

## Prerequisites

Before you begin, ensure you have met the following requirements:

* **Python 3.9+** installed.
* **`pip`** (Python package installer) installed.
* A **Telegram Bot Token** obtained from BotFather.
* A **Firebase project** with a **Realtime Database** enabled.
* A **Heroku account**.
* **Git** installed.

---

## Local Setup

Follow these steps to set up and run the bot on your local machine for development or testing.

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/YOUR_GITHUB_USERNAME/your-bot-repo-name.git](https://github.com/YOUR_GITHUB_USERNAME/your-bot-repo-name.git)
    cd your-bot-repo-name
    ```

2.  **Create a virtual environment:**
    ```bash
    python -m venv venv
    ```

3.  **Activate the virtual environment:**
    * **macOS/Linux:**
        ```bash
        source venv/bin/activate
        ```
    * **Windows (Command Prompt):**
        ```bash
        .\venv\Scripts\activate.bat
        ```
    * **Windows (PowerShell):**
        ```bash
        .\venv\Scripts\Activate.ps1
        ```

4.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

### Environment Variables

Your bot requires specific environment variables for its operation. Create a file named `.env` in the root directory of your project.

**`.env.template` (Example of expected environment variables - DO NOT put your actual secrets here):**

````

BOT\_TOKEN=YOUR\_TELEGRAM\_BOT\_TOKEN\_HERE
FIREBASE\_DB\_URL=YOUR\_FIREBASE\_DATABASE\_URL\_HERE
FIREBASE\_CRED\_BASE64=YOUR\_BASE64\_ENCODED\_FIREBASE\_SERVICE\_ACCOUNT\_JSON\_HERE \# For Heroku deployment

# For local development, you might use a serviceAccountKey.json file directly.

# If so, ensure it's in your project root and uncomment/adjust path below:

# FIREBASE\_SERVICE\_ACCOUNT\_KEY\_PATH=./serviceAccountKey.json

```

**Your actual `.env` file (which should be created but NOT committed to Git):**

```

BOT\_TOKEN=1234567890:ABC-DEF1234ghIkl-zyx57W2134asdEXAMPLE
FIREBASE\_DB\_URL=[https://your-project-id-default-rtdb.firebaseio.com/](https://www.google.com/url?sa=E&source=gmail&q=https://your-project-id-default-rtdb.firebaseio.com/)

# For local testing with a file, place your downloaded JSON file in the project root

# and ensure firebase\_utils.py's fallback path matches.

# FIREBASE\_CRED\_BASE64 is primarily for Heroku, you can leave it blank locally.

````
*(When running locally, `firebase_utils.py` is configured to first check for `FIREBASE_CRED_BASE64` and then fallback to `serviceAccountKey.json`. For local development, having `serviceAccountKey.json` directly in your project's root and correctly added to `.gitignore` is often simplest.)*

### Running Locally

After setup, you can run the bot on your local machine:

```bash
python main_movie_bot.py
````

-----

## Firebase Realtime Database Setup

Your bot leverages Firebase Realtime Database for persistent storage of movie data and user statistics.

1.  **Create a Firebase Project:**

      * Navigate to the [Firebase Console](https://console.firebase.google.com/).
      * Click "Add project" and follow the prompts to create a new project.

2.  **Create a Realtime Database:**

      * Within your Firebase project, go to the "Realtime Database" section under "Build" in the left-hand menu.
      * Click "Create database."
      * Choose your desired location.
      * **Security Rules:** For development, you can start in "test mode" (allowing read/write access), but **for production, highly recommend securing your rules** to prevent unauthorized access. Refer to Firebase documentation on Realtime Database security rules.

3.  **Generate Service Account Key (JSON):**

      * Go to "Project settings" (gear icon) -\> "Service accounts."
      * Click "Generate new private key" and then "Generate key." This will download a JSON file (e.g., `your-project-id-firebase-adminsdk-xxxxx-xxxxxxxxxx.json`).
      * **This file is highly sensitive\! Keep it secure and DO NOT commit it to your Git repository.**
      * Rename this file (e.g., to `serviceAccountKey.json`) and place it in your project's root for local testing if you choose not to use the base64 env var locally. **Ensure `serviceAccountKey.json` is added to your `.gitignore`.**

4.  **Obtain Database URL:**

      * Your database URL is found in the Firebase Console under the "Realtime Database" section. It usually looks like `https://your-project-id-default-rtdb.firebaseio.com/`. You'll need this for your environment variables.

-----

## Deployment to Heroku

This section details how to deploy your bot for continuous operation on Heroku.

### Heroku CLI Installation

If you haven't already, install the Heroku Command Line Interface (CLI): [Heroku CLI Installation Guide](https://devcenter.heroku.com/articles/heroku-cli)

### Creating a Heroku App

1.  **Log in to Heroku CLI:**

    ```bash
    heroku login
    ```

    Follow the browser authentication process.

2.  **Create a new Heroku app:**

    ```bash
    heroku create your-unique-app-name # Optional: provide a unique name, otherwise Heroku generates one.
    ```

    This command also sets up a Git remote named `heroku` pointing to your new app.

### Setting Heroku Config Vars

Heroku uses "Config Vars" to manage environment variables securely. You will set your `BOT_TOKEN`, `FIREBASE_DB_URL`, and the Firebase service account key content here.

1.  **Set `BOT_TOKEN`:**

    ```bash
    heroku config:set BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
    ```

2.  **Set `FIREBASE_DB_URL`:**

    ```bash
    heroku config:set FIREBASE_DB_URL=YOUR_FIREBASE_DATABASE_URL
    ```

3.  **Set `FIREBASE_CRED_BASE64` (Firebase Service Account Key):**

      * This is the recommended and most secure way to provide your Firebase credentials to Heroku.
      * First, get the content of your `serviceAccountKey.json` file.
      * Then, base64 encode it.
          * **macOS/Linux:**
            ```bash
            # Read content, remove newlines/spaces, then base64 encode
            BASE64_KEY=$(cat serviceAccountKey.json | tr -d '\n\r ' | base64)
            heroku config:set FIREBASE_CRED_BASE64="$BASE64_KEY"
            ```
          * **Windows (PowerShell):**
            ```powershell
            $jsonContent = Get-Content -Raw .\serviceAccountKey.json | Out-String
            $cleanedJson = $jsonContent -replace "`n", "" -replace "`r", "" -replace " ", ""
            $bytes = [System.Text.Encoding]::UTF8.GetBytes($cleanedJson)
            $base64String = [System.Convert]::ToBase64String($bytes)
            heroku config:set FIREBASE_CRED_BASE64="$base64String"
            ```
            *(Alternatively for Windows, you can open the `serviceAccountKey.json` file, copy its entire content, remove all newlines and unnecessary spaces, then use an online base64 encoder, and paste the result into the `heroku config:set` command.)*

### Deploying Your Bot

1.  **Ensure `requirements.txt` is up-to-date:**

    ```bash
    pip freeze > requirements.txt
    ```

2.  **Ensure you have a `Procfile`:**
    Create a file named `Procfile` (no extension) in the root of your project with the following content:

    ```
    worker: python main_movie_bot.py
    ```

3.  **Add all changes to Git and commit:**

    ```bash
    git add .
    git commit -m "Ready for Heroku deployment with Firebase configs"
    ```

4.  **Push your code to Heroku:**

    ```bash
    git push heroku main # Or `git push heroku master` if your default branch is master
    ```

5.  **Scale your worker dyno (if it's not already running):**

    ```bash
    heroku ps:scale worker=1 -a YOUR_APP_NAME
    ```

    *(Replace `YOUR_APP_NAME` with your Heroku app's actual name.)*

6.  **Monitor your bot's logs:**

    ```bash
    heroku logs --tail -a YOUR_APP_NAME
    ```

    This command is essential for real-time debugging and ensuring your bot starts correctly.

### Procfile Explained

The `Procfile` specifies the commands that are executed by Heroku's dynos. For a constantly running Telegram bot, the `worker` process type is appropriate. `worker: python main_movie_bot.py` tells Heroku to run your `main_movie_bot.py` script as a worker process.

-----

## Bot Usage

Here's how users can interact with the Telegram Movie Bot:

  * **`/start`**: Initiates the bot and sends a welcome message with available options.
  * **`🎬 Filmlar Ro'yxati` (button) or `/listallmovies`**: Displays a list of all movies currently available in the database, showing their codes and names.
  * **`❓ Yordam` (button) or `/userhelp`**: Provides a general help message on how to use the bot.
  * **Send a Movie Code**: If you know the exact code of a movie (e.g., `1` or `avatar`), simply send it as a text message, and the bot will send you the movie.
  * **Send a Movie Name**: Type part or all of a movie's name (e.g., `inception` or `avatar`), and the bot will search for matching titles. If multiple matches are found, it will provide options to select from.

-----

## Admin Commands

(Accessible only by configured `ADMIN_USER_IDS` in `main_movie_bot.py`)

  * **`/adminhelp`**: Displays a list of all administrative commands.
  * **`/myid`**: Shows your Telegram User ID (useful for adding yourself to `ADMIN_USER_IDS`).
  * **`/addmovie`**: Initiates a guided process to add a new movie:
    1.  Send the movie file (video or document).
    2.  Provide a unique code for the movie.
    3.  Provide the full title/name of the movie.
  * **`/deletemovie`**: Initiates a process to delete a movie by its code.
  * **`/cancel`**: Cancels any ongoing `addmovie` or `deletemovie` process.

-----

## Project Structure

```
.
├── main_movie_bot.py       # Main bot logic, handlers, and FSM states
├── firebase_utils.py       # Functions for interacting with Firebase Realtime Database
├── Procfile                # Heroku process definition for deployment
├── requirements.txt        # Python dependencies (generated via `pip freeze > requirements.txt`)
├── .env.template           # Template for environment variables (DO NOT COMMIT SENSITIVE DATA)
├── .gitignore              # Specifies files/directories to be ignored by Git
└── README.md               # This documentation file
```

-----

## Contributing

Contributions are welcome\! If you'd like to contribute, please follow these steps:

1.  Fork the repository.
2.  Create a new branch (`git checkout -b feature/your-feature-name`).
3.  Make your changes and ensure tests (if any) pass.
4.  Commit your changes (`git commit -m 'Add new feature X'`).
5.  Push to the branch (`git push origin feature/your-feature-name`).
6.  Open a Pull Request.

-----
